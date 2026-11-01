"""Android "SMS Backup & Restore" XML yedeğinden etiketlenecek aday mesajlar çıkarır.

Kullanım:
    python import_sms_backup.py sms-yedek.xml data/candidates.jsonl [--include-contacts] [--min-len 15]

- Sadece gelen mesajlar alınır (type=1).
- Varsayılan olarak rehberdeki kişilerden gelen mesajlar ALINMAZ (özel sohbetler).
- Metin hemen maskelenir; maskesiz metin hiçbir dosyaya yazılmaz.
- Aynı mesajın tekrarları (rakamlar farklı olsa bile) tek kayda indirilir.
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from mask_pii import make_id, mask_text


def sender_type(address: str) -> str:
    if not address:
        return "bilinmiyor"
    if re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", address):
        return "alfanumerik"
    digits = re.sub(r"\D", "", address)
    return "kisa_kod" if len(digits) <= 6 else "numara"


def is_contact(contact_name: str | None) -> bool:
    return bool(contact_name) and contact_name not in ("(Unknown)", "null")


def dedupe_key(text: str) -> str:
    return re.sub(r"\d", "0", re.sub(r"\s+", " ", text.lower())).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xml")
    parser.add_argument("out")
    parser.add_argument("--include-contacts", action="store_true", help="rehberdeki kişilerin mesajlarını da al")
    parser.add_argument("--min-len", type=int, default=15)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    stats = Counter()
    seen = set()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8") as f:
        for _, el in ET.iterparse(args.xml, events=("end",)):
            if el.tag != "sms":
                continue
            stats["toplam"] += 1
            attrs = el.attrib
            body = (attrs.get("body") or "").strip()
            el.clear()

            if attrs.get("type") != "1":
                stats["atlandi_giden"] += 1
                continue
            if is_contact(attrs.get("contact_name")) and not args.include_contacts:
                stats["atlandi_rehber"] += 1
                continue
            if len(body) < args.min_len:
                stats["atlandi_kisa"] += 1
                continue

            text, _ = mask_text(body)
            key = dedupe_key(text)
            if key in seen:
                stats["atlandi_tekrar"] += 1
                continue
            seen.add(key)

            address = attrs.get("address", "")
            stype = sender_type(address)
            date = ""
            if attrs.get("date", "").isdigit():
                date = datetime.fromtimestamp(int(attrs["date"]) / 1000, tz=timezone.utc).strftime("%Y-%m")

            record = {
                "id": make_id(text),
                "text": text,
                # Alfanumerik gönderici adı (YURTICI, ZIRAAT...) güçlü bir sinyal, korunur; numaralar korunmaz.
                "sender": address if stype == "alfanumerik" else stype,
                "sender_type": stype,
                "channel": "sms",
                "source": "kendi_gelen_kutusu",
                "is_synthetic": False,
                "date": date,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            stats["aday"] += 1

    print(f"{stats['aday']} aday mesaj → {out}")
    for k, v in stats.items():
        if k != "aday":
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
