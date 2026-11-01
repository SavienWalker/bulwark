"""Gerçek veri setine göndericiye göre sabit dev/test bölümü ekler (eval_split alanı).

Kullanım:
    python split_real.py data/real_tr.jsonl [data/real_email.jsonl ...]

Aynı göndericinin bütün mesajları aynı bölüme düşer; böylece dev'de görülen bir kurumun şablonu test'te
modele "tanıdık" gelmez. Bilinmeyen numaralar tek tek dağıtılır. Bölüm, gönderici adının özetinden
(hash) hesaplanır: dosyaya yeni mesaj eklense de eski mesajların bölümü değişmez.
- dev: hata analizi ve model seçimi için
- test: sadece son raporda kullanılır
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

NAMED = ("alfanumerik", "eposta")


def split_of(rec) -> str:
    key = rec["sender"] if rec.get("sender_type") in NAMED else rec["id"]
    return "dev" if int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16) % 2 == 0 else "test"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for name in sys.argv[1:]:
        p = Path(name)
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in rows:
            r["eval_split"] = split_of(r)
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(name, dict(Counter((r["eval_split"], r["label"]) for r in rows)))


if __name__ == "__main__":
    main()
