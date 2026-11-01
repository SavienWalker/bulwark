"""Veri seti dosyalarını şemaya, kişisel veri kalıntılarına ve tekrarlara karşı kontrol eder.

Kullanım:
    python validate_dataset.py data/seed_hard_tr.jsonl [data/real_tr.jsonl ...]

Hata varsa çıkış kodu 1 olur.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

from mask_pii import mask_text
from scam_schema import CATEGORIES, CHANNELS, DIFFICULTIES, HARD_TAGS, LABELS, REQUIRED_FIELDS, SOURCES

ENUMS = {
    "label": LABELS,
    "category": CATEGORIES,
    "difficulty": DIFFICULTIES,
    "channel": CHANNELS,
    "source": SOURCES,
}


def norm(text: str) -> str:
    return re.sub(r"\d", "0", re.sub(r"\s+", " ", text.lower())).strip()


def main():
    if len(sys.argv) < 2:
        sys.exit("Kullanım: python validate_dataset.py dosya.jsonl [dosya2.jsonl ...]")
    sys.stdout.reconfigure(encoding="utf-8")

    errors, warnings = [], []
    records = []
    ids, texts = {}, {}

    for path in map(Path, sys.argv[1:]):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            where = f"{path.name}:{n}"
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{where}: geçersiz JSON ({e})")
                continue
            records.append(r)
            rid = r.get("id", "?")

            for field in REQUIRED_FIELDS:
                if field not in r:
                    errors.append(f"{where} [{rid}]: '{field}' alanı eksik")
            for field, allowed in ENUMS.items():
                if field in r and r[field] not in allowed:
                    errors.append(f"{where} [{rid}]: {field}='{r[field]}' geçersiz")
            if not isinstance(r.get("is_synthetic"), bool):
                errors.append(f"{where} [{rid}]: is_synthetic true/false olmalı")
            for tag in r.get("hard_tags", []):
                if tag not in HARD_TAGS:
                    errors.append(f"{where} [{rid}]: hard_tag '{tag}' geçersiz")
            if r.get("source") in ("elle_yazildi", "sentetik") and r.get("is_synthetic") is False:
                errors.append(f"{where} [{rid}]: source={r['source']} ama is_synthetic=false")

            if rid in ids:
                errors.append(f"{where}: id '{rid}' tekrar ediyor (ilk: {ids[rid]})")
            ids[rid] = where

            text = r.get("text", "")
            key = norm(text)
            if key in texts:
                warnings.append(f"{where} [{rid}]: metin {texts[key]} ile aynı")
            texts[key] = where

            masked, counts = mask_text(text)
            if counts:
                errors.append(f"{where} [{rid}]: maskelenmemiş veri olabilir: {dict(counts)}")

            if r.get("label") in ("fraud", "spam") and not r.get("explanation"):
                warnings.append(f"{where} [{rid}]: açıklama (explanation) yok")

    # Özet
    print(f"{len(records)} kayıt, {len(errors)} hata, {len(warnings)} uyarı\n")
    for title, key in (("Etiket", "label"), ("Zorluk", "difficulty"), ("Kaynak", "source"), ("Kanal", "channel")):
        c = Counter(r.get(key, "-") for r in records)
        print(f"{title}: " + ", ".join(f"{k}={v}" for k, v in c.most_common()))
    synth = sum(r.get("is_synthetic") is True for r in records)
    amb = sum(r.get("ambiguous") is True for r in records)
    pairs = Counter(r["pair"] for r in records if r.get("pair"))
    print(f"Sentetik: {synth}/{len(records)}   Belirsiz: {amb}   Karşıt çift: {sum(v >= 2 for v in pairs.values())}")
    print("Kategori: " + ", ".join(f"{k}={v}" for k, v in Counter(r.get("category") for r in records).most_common()))

    if warnings:
        print("\nUyarılar:")
        for w in warnings:
            print("  " + w)
    if errors:
        print("\nHatalar:")
        for e in errors:
            print("  " + e)
        sys.exit(1)


if __name__ == "__main__":
    main()
