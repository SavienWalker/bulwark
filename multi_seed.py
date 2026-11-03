"""Aynı eğitimi farklı seed'lerle tekrarlayan modelleri ölçüp ortalama ± sapma raporlar.

Kullanım:
    python multi_seed.py "v5=checkpoints/v5,checkpoints/v5-s21,checkpoints/v5-s42" \
                         "v5-famho=checkpoints/v5-famho,checkpoints/v5-famho-s21,checkpoints/v5-famho-s42"

Ölçümler (Bulwark eşiği 0.6; test yarısı kullanılmaz):
- gerçek SMS dev yarısı: temizde yanlış alarm, istenmeyeni yakalama
- dışarıda bırakılan ailelerin sentetik mesajları ve zor set karşılıkları: yakalama
- zor set v2: dolandırıcılık yakalama, karşıt çiftlerde ikisi de doğru
"""
import json
import re
import statistics
import sys
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from family_holdout import FAMILIES, SLICE
from test_rival import predict

sys.stdout.reconfigure(encoding="utf-8")
T = 0.6
DEFAULT_SEED = 13  # train.py'nin varsayılanı; klasör adında -sNN yoksa bu seed kullanılmıştır


def read(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def load_sets():
    sms = [r for r in read("data/real_tr.jsonl") if r.get("eval_split") == "dev" and not r.get("ambiguous")]
    held = read(SLICE)
    hard_ids = {i for f in FAMILIES.values() for i in f["hard"]}
    hard_held = [r for p in ("data/seed_hard_tr.jsonl", "data/seed_hard2_tr.jsonl") for r in read(p) if r["id"] in hard_ids]
    hard2 = [r for r in read("data/seed_hard2_tr.jsonl") if not r.get("ambiguous")]
    return {"sms": sms, "held": held, "hard_held": hard_held, "hard2": hard2}


def score(model_dir, sets, device):
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device).eval()
    id2 = {int(k): v.lower() for k, v in model.config.id2label.items()}

    def run(rows):
        out = []
        for r, p in zip(rows, predict(model, tok, [r["text"] for r in rows], 16)):
            d = {id2[i]: v for i, v in enumerate(p)}
            out.append((r, d["fraud"] + d["spam"] > T, max(d, key=d.get)))
        return out

    m = {}
    sms = run(sets["sms"])
    leg = [u for r, u, _ in sms if r["label"] == "legitimate"]
    bad = [u for r, u, _ in sms if r["label"] != "legitimate"]
    m["SMS dev: temizde yanlış alarm ↓"] = sum(leg) / len(leg)
    m["SMS dev: istenmeyeni yakalama ↑"] = sum(bad) / len(bad)
    held = run(sets["held"])
    m["Görülmemiş aile, sentetik: yakalama ↑"] = sum(u for _, u, _ in held) / len(held)
    hh = run(sets["hard_held"])
    m["Görülmemiş aile, zor set: yakalama ↑"] = sum(u for _, u, _ in hh) / len(hh)
    h2 = run(sets["hard2"])
    fr = [u for r, u, _ in h2 if r["label"] == "fraud"]
    m["Zor set v2: fraud yakalama ↑"] = sum(fr) / len(fr)
    pairs = {}
    for r, _, pred in h2:
        if r.get("pair"):
            pairs.setdefault(r["pair"], []).append(pred == r["label"])
    full = [v for v in pairs.values() if len(v) >= 2]
    m["Zor set v2: karşıt çift ikisi de doğru ↑"] = sum(all(v) for v in full) / len(full)
    del model
    torch.cuda.empty_cache()
    return m


def main():
    groups = {}
    for arg in sys.argv[1:]:
        name, dirs = arg.split("=", 1)
        groups[name] = dirs.split(",")
    sets = load_sets()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    results = {name: [score(d, sets, device) for d in dirs] for name, dirs in groups.items()}

    keys = list(next(iter(results.values()))[0])
    names = list(results)
    print("| Ölçüm | " + " | ".join(f"{n} (n={len(results[n])})" for n in names) + " |")
    print("|---|" + "---|" * len(names))
    for k in keys:
        cells = []
        for n in names:
            vals = [r[k] * 100 for r in results[n]]
            sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
            cells.append(f"{statistics.mean(vals):.1f} ± {sd:.1f}  [{min(vals):.0f}–{max(vals):.0f}]")
        print(f"| {k} | " + " | ".join(cells) + " |")

    # Eşleştirilmiş karşılaştırma: iki grup aynı seed sırasıyla verildiyse her seed'deki farkı (B − A) gösterir.
    # Ortalama ± sapma seed gürültüsünü gerçek farktan ayıramaz; aynı seed'deki fark ayırır.
    if len(names) == 2 and len(results[names[0]]) == len(results[names[1]]):
        a, b = names
        seeds = [re.search(r"-s(\d+)$", d).group(1) if re.search(r"-s(\d+)$", d) else str(DEFAULT_SEED)
                 for d in groups[a]]
        for k in ("Görülmemiş aile, sentetik: yakalama ↑", "SMS dev: temizde yanlış alarm ↓"):
            print(f"\n**Eşleştirilmiş: {k}** (Δ = {b} − {a}, puan)\n")
            print(f"| seed | {a} | {b} | Δ |\n|---|---|---|---|")
            deltas = []
            for s, ra, rb in zip(seeds, results[a], results[b]):
                d = (rb[k] - ra[k]) * 100
                deltas.append(d)
                print(f"| {s} | {ra[k] * 100:.1f} | {rb[k] * 100:.1f} | {d:+.1f} |")
            print(f"| ortalama Δ | | | **{statistics.mean(deltas):+.1f}** (en düşük {min(deltas):+.1f}, en yüksek {max(deltas):+.1f}) |")


if __name__ == "__main__":
    main()
