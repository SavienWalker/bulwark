"""Rakip modelin (ya da başka bir mmBERT checkpoint'inin) üstüne sınıflandırıcı fine-tuning.

Kullanım:
    python train.py data/train_synth.jsonl --out checkpoints/v1 [--base Horizon-Labs/phishing-scam-detector-base]
                    [--epochs 3] [--lr 2e-5] [--batch 16] [--max-len 256] [--train-embeddings]

- Kelime gömmeleri (256k sözlük, parametrelerin ~%64'ü) varsayılan olarak dondurulur: 6 GB GPU'ya sığar ve
  az veriyle sözlüğün bozulmasını önler.
- Doğrulama: verideki split=val kayıtları (eğitimde hiç görülmeyen şablonlar). En iyi makro F1'li
  epoch kaydedilir.
- Test setleri burada kullanılmaz; ölçüm için: python test_rival.py <test.jsonl> --model checkpoints/v1
"""
import argparse
import json
import math
import random
import sys
import time
from collections import Counter
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

sys.stdout.reconfigure(encoding="utf-8")


def macro_f1(gold, pred, labels):
    f1s = {}
    for c in labels:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s[c] = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return sum(f1s.values()) / len(f1s), f1s


def batches(items, size, shuffle, rng):
    idx = list(range(len(items)))
    if shuffle:
        rng.shuffle(idx)
    for i in range(0, len(idx), size):
        yield [items[j] for j in idx[i : i + size]]


@torch.no_grad()
def evaluate(model, tok, rows, label2id, args, device):
    model.eval()
    gold, pred = [], []
    for b in batches(rows, args.batch * 2, False, None):
        enc = tok([r["text"] for r in b], truncation=True, max_length=args.max_len, padding=True,
                  return_tensors="pt").to(device)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device == "cuda"):
            logits = model(**enc).logits
        pred += logits.argmax(-1).tolist()
        gold += [label2id[r["label"]] for r in b]
    model.train()
    return gold, pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="Horizon-Labs/phishing-scam-detector-base")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--warmup", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--train-embeddings", action="store_true")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    rows = [json.loads(l) for l in Path(args.data).read_text(encoding="utf-8").splitlines() if l.strip()]
    train = [r for r in rows if r.get("split", "train") == "train"]
    val = [r for r in rows if r.get("split") == "val"]
    print(f"Eğitim {len(train)} / doğrulama {len(val)}  ·  {dict(Counter(r['label'] for r in train))}")

    tok = AutoTokenizer.from_pretrained(args.base)
    model = AutoModelForSequenceClassification.from_pretrained(args.base, num_labels=3)
    label2id = {v.lower(): int(k) for k, v in model.config.id2label.items()}
    assert set(label2id) == {"legitimate", "spam", "fraud"}, model.config.id2label

    if not args.train_embeddings:
        for p in model.get_input_embeddings().parameters():
            p.requires_grad = False
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Eğitilen parametre: {trainable / 1e6:.0f}M / {total / 1e6:.0f}M  ·  cihaz: {device}")
    model.to(device).train()

    # Sınıf dengesizliği için kayıp ağırlığı (az olan sınıf daha ağır)
    counts = Counter(label2id[r["label"]] for r in train)
    weights = torch.tensor([len(train) / (3 * counts[i]) for i in range(3)], device=device)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)

    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.01)
    steps = math.ceil(len(train) / args.batch) * args.epochs
    sched = get_linear_schedule_with_warmup(opt, int(steps * args.warmup), steps)

    names = {i: l for l, i in label2id.items()}
    best, out = -1.0, Path(args.out)
    for epoch in range(1, args.epochs + 1):
        t0, total_loss, n = time.time(), 0.0, 0
        for b in batches(train, args.batch, True, rng):
            enc = tok([r["text"] for r in b], truncation=True, max_length=args.max_len, padding=True,
                      return_tensors="pt").to(device)
            y = torch.tensor([label2id[r["label"]] for r in b], device=device)
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device == "cuda"):
                logits = model(**enc).logits
            loss = loss_fn(logits.float(), y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            total_loss += loss.item()
            n += 1
        gold, pred = evaluate(model, tok, val, label2id, args, device)
        f1, per = macro_f1(gold, pred, range(3))
        per_txt = "  ".join(f"{names[i]}={v:.2f}" for i, v in per.items())
        mem = torch.cuda.max_memory_allocated() / 2**30 if device == "cuda" else 0
        print(f"epoch {epoch}: kayıp {total_loss / n:.4f}  val makro-F1 {f1:.3f} ({per_txt})  "
              f"{time.time() - t0:.0f} sn  GPU tepe {mem:.1f} GB")
        if f1 > best:
            best = f1
            out.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(out)
            tok.save_pretrained(out)
            (out / "train_args.json").write_text(json.dumps({**vars(args), "val_macro_f1": f1, "epoch": epoch},
                                                            ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ↳ en iyi model kaydedildi → {out}")
    print(f"Bitti. En iyi val makro-F1: {best:.3f}")


if __name__ == "__main__":
    main()
