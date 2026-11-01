"""Eğitim verisinde test mesajlarına çok benzeyen kayıtları bulur ve isteğe bağlı olarak atar.

Kullanım:
    python check_leakage.py data/train_synth.jsonl [--drop] [--threshold 0.5]

Benzerlik: label.py'deki şablon kelime kümesi (rakamlar ve linkler normalize) üzerinden Jaccard.
--drop verilirse eşiği aşan kayıtlar eğitim dosyasından çıkarılır (yedek: <dosya>.before_leakcheck).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from label import template_tokens

TEST_FILES = ["data/real_tr.jsonl", "data/real_email.jsonl", "data/seed_hard_tr.jsonl", "data/seed_hard2_tr.jsonl",
              "data/candidates_email.jsonl", "data/candidates_hard2.jsonl"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("train")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--drop", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    tests = []
    for f in TEST_FILES:
        if Path(f).exists():
            tests += [(f, json.loads(l)) for l in Path(f).read_text(encoding="utf-8").splitlines() if l.strip()]
    test_tokens = [(f, r, template_tokens(r["text"])) for f, r in tests]
    print(f"{len(tests)} test mesajı yüklendi.")

    train_path = Path(args.train)
    train = [json.loads(l) for l in train_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    keep, leaks = [], []
    for r in train:
        tok = template_tokens(r["text"])
        best, match = 0.0, None
        for f, t, tt in test_tokens:
            if not tok or not tt:
                continue
            j = len(tok & tt) / len(tok | tt)
            if j > best:
                best, match = j, (f, t)
        if best >= args.threshold:
            leaks.append((best, r, match))
        else:
            keep.append(r)

    by_template = {}
    for best, r, (f, t) in leaks:
        by_template.setdefault(r.get("template", "-"), []).append((best, r, f, t))
    print(f"Eşiği ({args.threshold}) aşan eğitim kaydı: {len(leaks)}/{len(train)}")
    for tid, items in sorted(by_template.items(), key=lambda kv: -len(kv[1])):
        best, r, f, t = max(items, key=lambda x: x[0])
        print(f"  {tid}: {len(items)} kayıt, en yüksek {best:.2f} ↔ {Path(f).name} [{t['id']}]")
        print(f"      eğitim: {r['text'][:90]!r}")
        print(f"      test:   {t['text'][:90]!r}")

    if args.drop and leaks:
        shutil.copy(train_path, train_path.with_suffix(".before_leakcheck"))
        train_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep), encoding="utf-8")
        print(f"{len(leaks)} kayıt atıldı → {train_path} ({len(keep)} kayıt kaldı)")


if __name__ == "__main__":
    main()
