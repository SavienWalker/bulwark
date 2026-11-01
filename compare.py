"""Birden çok modeli tüm test setlerinde yan yana ölçer.

Kullanım:
    python compare.py checkpoints/v1 [başka_model ...] [--threshold 0.5]

Rakip (Horizon-Labs/phishing-scam-detector-base) her zaman ilk sütundur. Onaylanmamış setler için
aday dosyası + <çıktı>.claude.jsonl önerileri birleştirilir ve tabloda "(ön)" diye işaretlenir.
ambiguous=true kayıtlar metriklere girmez.
"""
import argparse
import json
import sys
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from test_rival import MODEL_ID, predict

sys.stdout.reconfigure(encoding="utf-8")

# (ad, onaylı dosya, onaysızsa aday dosyası, öneri dosyası)
SETS = [
    ("Gerçek SMS", "data/real_tr.jsonl", None, None),
    ("Gerçek e-posta", "data/real_email.jsonl", "data/candidates_email.jsonl", "data/real_email.claude.jsonl"),
    ("Zor set v1", "data/seed_hard_tr.jsonl", None, None),
    ("Zor set v2", "data/seed_hard2_tr.jsonl", "data/candidates_hard2.jsonl", "data/seed_hard2_tr.claude.jsonl"),
    ("Gerçek diğer (sahte sayfa, DM; ekran görüntüsünden)", "data/real_misc.jsonl", None, None),
    ("İngilizce SMS (UCI, unutma kontrolü)", "data/external/en_eval.jsonl", None, None),
]


def read(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def load_set(done, cand, sugg):
    if Path(done).exists():
        rows = read(done)
        if not cand or len(rows) >= len(read(cand)):
            return rows, False
    if cand and Path(cand).exists() and Path(sugg).exists():
        c = {r["id"]: r for r in read(cand)}
        return [{**c[s["id"]], **s} for s in read(sugg) if s["id"] in c], True
    return [], False


def metrics(rows, probs, id2label, t):
    res = []
    for r, p in zip(rows, probs):
        d = {id2label[i]: v for i, v in enumerate(p)}
        res.append({**r, "pf": d["fraud"], "un": d["fraud"] + d["spam"],
                    "pred": max(d, key=d.get)})
    m = [r for r in res if not r.get("ambiguous")]
    leg = [r for r in m if r["label"] == "legitimate"]
    fr = [r for r in m if r["label"] == "fraud"]
    sp = [r for r in m if r["label"] == "spam"]
    out = {
        "Doğruluk (3 sınıf)": (sum(r["pred"] == r["label"] for r in m), len(m)),
        "Temizde yanlış alarm ↓": (sum(r["un"] > t for r in leg), len(leg)),
        "Temize 'fraud' demesi ↓": (sum(r["pf"] > t for r in leg), len(leg)),
        "Fraud yakalama ↑": (sum(r["pf"] > t for r in fr), len(fr)),
        "Spam doğru ↑": (sum(r["pred"] == "spam" for r in sp), len(sp)),
        "İstenmeyeni yakalama (spam+fraud) ↑": (sum(r["un"] > t for r in fr + sp), len(fr + sp)),
    }
    pairs = {}
    for r in m:
        if r.get("pair"):
            pairs.setdefault(r["pair"], []).append(r["pred"] == r["label"])
    full = [v for v in pairs.values() if len(v) >= 2]
    if full:
        out["Karşıt çift ikisi de doğru ↑"] = (sum(all(v) for v in full), len(full))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev",
                    help="eval_split alanı olan setlerde hangi yarı ölçülsün (test sadece son rapor için)")
    args = ap.parse_args()
    models = [MODEL_ID] + args.models
    device = "cuda" if torch.cuda.is_available() else "cpu"

    data = []
    for name, done, cand, sugg in SETS:
        rows, prelim = load_set(done, cand, sugg)
        if args.split != "all" and rows and "eval_split" in rows[0]:
            rows = [r for r in rows if r["eval_split"] == args.split]
            name = f"{name} [{args.split}]"
        data.append((name, rows, prelim))
    table = {}
    for mid in models:
        tok = AutoTokenizer.from_pretrained(mid)
        model = AutoModelForSequenceClassification.from_pretrained(mid).to(device).eval()
        id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}
        for name, rows, prelim in data:
            if rows:
                table[(name, mid)] = metrics(rows, predict(model, tok, [r["text"] for r in rows], 16), id2label,
                                             args.threshold)
        del model
        torch.cuda.empty_cache()

    short = ["rakip"] + [Path(m).name for m in args.models]
    for name, rows, prelim in data:
        if not rows:
            continue
        print(f"\n## {name}{' (ön: Claude önerileri, onaylanmadı)' if prelim else ''} — {len(rows)} mesaj")
        print(f"| Ölçüm | " + " | ".join(short) + " |")
        print("|---|" + "---|" * len(short))
        for key in table[(name, models[0])]:
            cells = []
            for mid in models:
                k, n = table[(name, mid)][key]
                cells.append(f"{k}/{n} ({k / n:.0%})" if n else "-")
            print(f"| {key} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
