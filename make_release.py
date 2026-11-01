"""Hugging Face'e yüklenecek iki klasörü hazırlar (yükleme yapmaz).

Kullanım:
    python make_release.py [--model checkpoints/v5]

- release/bulwark-scam-detector/ : model ağırlıkları + tokenizer + önerilen eşik
- release/bulwark-bench-tr/      : test setleri, yayın için temizlenmiş alanlarla

Gönderici alanında rakam dizisi varsa (telefon numarası) sadece türü bırakılır; iOS'un "(filtered)"/"(smsft)"
ekleri silinir. Sonunda bütün metinler mask_pii ve private_names.txt ile yeniden taranır; kalan kişisel
veri varsa betik hata verir ve klasörü yayına hazır saymaz.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from mask_pii import PRIVATE_NAMES_RE, mask_text

ROOT = Path(__file__).parent
KEEP = ["id", "text", "label", "category", "difficulty", "channel", "source", "is_synthetic", "hard_tags",
        "explanation", "pair", "ambiguous", "sender", "sender_type", "date", "labeled_by", "eval_split"]
DATASETS = {
    "real_sms.jsonl": "data/real_tr.jsonl",
    "real_email.jsonl": "data/real_email.jsonl",
    "real_other.jsonl": "data/real_misc.jsonl",
    "hard_synthetic_v1.jsonl": "data/seed_hard_tr.jsonl",
    "hard_synthetic_v2.jsonl": "data/seed_hard2_tr.jsonl",
}
MODEL_FILES = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"]
THRESHOLD = 0.6


def clean_sender(rec):
    s = rec.get("sender")
    if not s:
        return
    s = re.sub(r"\((filtered|smsft)\)", "", s).strip()
    rec["sender"] = rec.get("sender_type", "bilinmiyor") if re.search(r"\d{6,}", s) or not s else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="checkpoints/v5")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    mdir = ROOT / "release/bulwark-scam-detector"
    mdir.mkdir(parents=True, exist_ok=True)
    for f in MODEL_FILES:
        shutil.copy(ROOT / args.model / f, mdir / f)
    (mdir / "bulwark_config.json").write_text(json.dumps(
        {"recommended_threshold": THRESHOLD, "threshold_applies_to": "p_spam + p_fraud",
         "base_model": "Horizon-Labs/phishing-scam-detector-base", "checkpoint": args.model},
        indent=2), encoding="utf-8")

    ddir = ROOT / "release/bulwark-bench-tr/data"
    ddir.mkdir(parents=True, exist_ok=True)
    problems, counts = [], {}
    for out_name, src in DATASETS.items():
        rows = [json.loads(l) for l in (ROOT / src).read_text(encoding="utf-8").splitlines() if l.strip()]
        out = []
        for r in rows:
            r = {k: r[k] for k in KEEP if k in r}
            clean_sender(r)
            _, found = mask_text(r["text"])
            if found:
                problems.append((out_name, r["id"], dict(found)))
            if PRIVATE_NAMES_RE and PRIVATE_NAMES_RE.search(r["text"] + " " + str(r.get("sender", ""))):
                problems.append((out_name, r["id"], "private_names"))
            out.append(r)
        (ddir / out_name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
        counts[out_name] = len(out)

    print("Model →", mdir)
    print("Veri  →", ddir, counts)
    if problems:
        for p in problems:
            print("  KİŞİSEL VERİ ŞÜPHESİ:", p)
        sys.exit(f"{len(problems)} kayıtta kişisel veri şüphesi var; yayınlamadan önce düzeltin.")
    print("Kişisel veri taraması temiz.")


if __name__ == "__main__":
    main()
