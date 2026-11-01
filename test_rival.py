"""Rakip modeli (Horizon-Labs/phishing-scam-detector-base) Türkçe örneklerle test eder.

Kullanım:
    python test_rival.py [mesaj_dosyasi.jsonl] [--threshold 0.5] [--out results_rival.csv]

Çıktı: konsola özet tablo + CSV. ambiguous=true kayıtlar gösterilir ama metriklere girmez.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_ID = "Horizon-Labs/phishing-scam-detector-base"
MAX_LEN = 384  # model kartındaki kesme uzunluğu

sys.stdout.reconfigure(encoding="utf-8")


def load_messages(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def predict(model, tokenizer, texts, batch_size=8):
    probs = []
    device = next(model.parameters()).device
    for i in range(0, len(texts), batch_size):
        batch = tokenizer(
            texts[i : i + batch_size],
            truncation=True,
            max_length=MAX_LEN,
            padding=True,
            return_tensors="pt",
        ).to(device)
        with torch.no_grad():
            logits = model(**batch).logits.float()
        probs.extend(torch.softmax(logits, dim=-1).tolist())
    return probs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("messages", nargs="?", default="test_messages_tr.jsonl")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--out", default="results_rival.csv")
    parser.add_argument("--model", default=MODEL_ID, help="Hugging Face kimliği ya da yerel checkpoint klasörü")
    args = parser.parse_args()

    messages = load_messages(args.messages)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model)
    model.to("cuda" if torch.cuda.is_available() else "cpu").eval()

    id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}
    print(f"Etiketler: {id2label}")
    label2id = {v: k for k, v in id2label.items()}
    if not {"fraud", "spam", "legitimate"} <= label2id.keys():
        sys.exit("Beklenen etiket isimleri (fraud/spam/legitimate) bulunamadı, config'e bak.")

    probs = predict(model, tokenizer, [m["text"] for m in messages])

    rows = []
    for m, p in zip(messages, probs):
        p_fraud = p[label2id["fraud"]]
        p_spam = p[label2id["spam"]]
        p_legit = p[label2id["legitimate"]]
        pred = id2label[max(range(len(p)), key=p.__getitem__)]
        rows.append(
            {
                "id": m["id"],
                "label": m["label"],
                "group": m.get("group") or m.get("category", "-"),
                "difficulty": m.get("difficulty", "-"),
                "ambiguous": m.get("ambiguous", False),
                "pred": pred,
                "p_fraud": round(p_fraud, 3),
                "p_spam": round(p_spam, 3),
                "p_legit": round(p_legit, 3),
                "unwanted": round(p_fraud + p_spam, 3),
                "correct": pred == m["label"],
                "text": m["text"],
            }
        )

    # Mesaj bazında sonuçlar
    print(f"\n{'id':<4} {'gerçek':<11} {'tahmin':<11} {'fraud':>6} {'spam':>6} {'legit':>6}  metin")
    for r in rows:
        mark = "? " if r["ambiguous"] else ("  " if r["correct"] else "✗ ")
        print(
            f"{r['id']:<4} {r['label']:<11} {r['pred']:<11} "
            f"{r['p_fraud']:>6.2f} {r['p_spam']:>6.2f} {r['p_legit']:>6.2f}  {mark}{r['text'][:60]}"
        )

    # Özet metrikler
    t = args.threshold
    scored = [r for r in rows if not r["ambiguous"]]  # belirsizler metriklere girmez
    by_label = defaultdict(list)
    for r in scored:
        by_label[r["label"]].append(r)

    fraud = by_label["fraud"]
    legit = by_label["legitimate"]
    hard_legit = [r for r in legit if r["group"].startswith("zor_") or r["difficulty"] == "zor"]
    chat = [r for r in legit if r["group"] == "sohbet"]

    def pct(n, d):
        return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "-"

    print("\n=== Özet ===")
    if len(scored) < len(rows):
        print(f"(Belirsiz {len(rows) - len(scored)} mesaj metriklere dahil edilmedi)")
    print(f"Genel doğruluk (3 sınıf):              {pct(sum(r['correct'] for r in scored), len(scored))}")
    hard_fraud = [r for r in fraud if r["difficulty"] == "zor"]
    if hard_fraud:
        print(f"Zor dolandırıcılık yakalama:           {pct(sum(r['p_fraud'] > t for r in hard_fraud), len(hard_fraud))}")
    print(f"Dolandırıcılık yakalama (P(fraud)>{t}): {pct(sum(r['p_fraud'] > t for r in fraud), len(fraud))}")
    print(f"Spam doğru etiket:                     {pct(sum(r['pred'] == 'spam' for r in by_label['spam']), len(by_label['spam']))}")
    print(f"Yanlış alarm, zor temiz (unwanted>{t}): {pct(sum(r['unwanted'] > t for r in hard_legit), len(hard_legit))}")
    print(f"Yanlış alarm, sohbet (unwanted>{t}):    {pct(sum(r['unwanted'] > t for r in chat), len(chat))}")

    print("\nGruplara göre doğruluk:")
    by_group = defaultdict(list)
    for r in scored:
        by_group[(r["label"], r["group"])].append(r["correct"])
    for (label, group), vals in sorted(by_group.items()):
        print(f"  {label:<11} {group:<13} {pct(sum(vals), len(vals))}")

    out = Path(args.out)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nDetaylı sonuçlar: {out}")


if __name__ == "__main__":
    main()
