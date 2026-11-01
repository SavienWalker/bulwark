"""UCI SMS Spam Collection'dan (İngilizce, CC BY 4.0) unutma kontrolü için iki set kurar.

Kullanım:
    python build_english.py

- data/external/en_eval.jsonl   : ayrılmış yarı, sadece ölçüm (ham → legitimate, spam → spam)
- data/external/en_replay.jsonl : diğer yarı, eğitime karışır. ham → legitimate; spam mesajlarının
  spam/fraud ayrımı rakip modelin kendi tahmininden alınır (damıtma), böylece model rakibin İngilizce
  davranışını korur.
Kaynak: https://archive.ics.uci.edu/dataset/228/sms+spam+collection (Almeida & Hidalgo, 2011)
"""
import json
import random
import sys
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from test_rival import MODEL_ID, predict

ROOT = Path(__file__).parent
SRC = ROOT / "data/external/uci_sms/SMSSpamCollection"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    for i, line in enumerate(SRC.read_text(encoding="utf-8", errors="replace").splitlines()):
        tag, _, text = line.partition("\t")
        if text.strip():
            rows.append({"id": f"uci-{i:05d}", "text": text.strip(), "uci": tag})
    random.Random(7).shuffle(rows)
    half = len(rows) // 2
    evals, replay = rows[:half], rows[half:]

    for r in evals:
        r.update(label="legitimate" if r["uci"] == "ham" else "spam", category="diger", difficulty="orta",
                 channel="sms", source="bagis", is_synthetic=False)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID).to(device).eval()
    id2 = {int(k): v.lower() for k, v in model.config.id2label.items()}
    spam_rows = [r for r in replay if r["uci"] == "spam"]
    for r, p in zip(spam_rows, predict(model, tok, [r["text"] for r in spam_rows], 32)):
        d = {id2[i]: v for i, v in enumerate(p)}
        r["label"] = "fraud" if d["fraud"] > d["spam"] else "spam"
    for r in replay:
        r.setdefault("label", "legitimate")
        r.update(category="diger", channel="sms", source="bagis", is_synthetic=False, template="uci", split="train")

    out = ROOT / "data/external"
    (out / "en_eval.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in evals), encoding="utf-8")
    (out / "en_replay.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in replay), encoding="utf-8")
    from collections import Counter
    print("eval:", dict(Counter(r["label"] for r in evals)), " replay:", dict(Counter(r["label"] for r in replay)))


if __name__ == "__main__":
    main()
