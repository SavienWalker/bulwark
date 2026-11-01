"""Bir modelin "istenmeyen" (spam+fraud) eşiğini dev verisinde tarar.

Kullanım:
    python sweep.py checkpoints/v5 [--thresholds 0.5,0.6,0.7,0.8,0.9]

Gerçek SMS'in sadece dev yarısı ve e-posta geliştirme seti kullanılır; test yarısına dokunulmaz.
Her eşik için: temiz mesajlarda yanlış alarm (düşük iyi) ve istenmeyeni yakalama (yüksek iyi).
"""
import argparse
import json
import sys
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from compare import load_set
from test_rival import predict

sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--thresholds", default="0.5,0.6,0.7,0.8,0.9")
    args = ap.parse_args()
    ts = [float(x) for x in args.thresholds.split(",")]

    sms = [r for r in json.loads("[" + ",".join(Path("data/real_tr.jsonl").read_text(encoding="utf-8").splitlines()) + "]")
           if r.get("eval_split") == "dev"]
    email, _ = load_set("data/real_email.jsonl", "data/candidates_email.jsonl", "data/real_email.claude.jsonl")
    rows = [r for r in sms + email if not r.get("ambiguous")]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model).to(device).eval()
    id2 = {int(k): v.lower() for k, v in model.config.id2label.items()}
    probs = predict(model, tok, [r["text"] for r in rows], 16)
    un = [sum(p[i] for i in id2 if id2[i] != "legitimate") for p in probs]

    leg = [u for r, u in zip(rows, un) if r["label"] == "legitimate"]
    bad = [u for r, u in zip(rows, un) if r["label"] != "legitimate"]
    print(f"{args.model}: dev SMS + e-posta, {len(leg)} temiz / {len(bad)} istenmeyen")
    print("| Eşik | Temize yanlış alarm ↓ | İstenmeyeni yakalama ↑ |\n|---|---|---|")
    for t in ts:
        fa, hit = sum(u > t for u in leg), sum(u > t for u in bad)
        print(f"| {t:.2f} | {fa}/{len(leg)} ({fa / len(leg):.0%}) | {hit}/{len(bad)} ({hit / len(bad):.0%}) |")


if __name__ == "__main__":
    main()
