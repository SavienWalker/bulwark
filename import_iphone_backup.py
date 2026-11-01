"""iPhone'un iTunes / Apple Aygıtları yedeğinden etiketlenecek aday mesajlar çıkarır.

Şifreli yedekte parola sorulur (iphone_backup_decrypt gerekir). Sadece sms.db geçici bir klasöre
çözülür, iş bitince silinir; yedeğin kendisi şifreli kalır.

Kullanım:
    python import_iphone_backup.py data/candidates.jsonl [--backup YEDEK_KLASORU] [--include-replied]

- --backup verilmezse Windows'taki varsayılan yedek klasörlerinde en yeni yedek kullanılır.
- Sadece gelen mesajlar alınır. Grup sohbetleri alınmaz.
- Varsayılan olarak SENİN CEVAP VERDİĞİN kişilerin mesajları ALINMAZ (özel sohbetler).
  Kurumlar ve dolandırıcılar genelde cevapsız kalır; arkadaşlar ve aile elenir.
- Metin hemen maskelenir; maskesiz metin hiçbir dosyaya yazılmaz. Yedeğe yazma yapılmaz.
"""
import argparse
import getpass
import json
import os
import plistlib
import sqlite3
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from import_sms_backup import dedupe_key, sender_type
from mask_pii import make_id, mask_text

# HomeDomain-Library/SMS/sms.db dosyasının yedekteki SHA1 adı
SMS_DB_HASH = "3d0d7e5fb2ce288813306e4d4636395e047a3d28"
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
DEFAULT_ROOTS = [
    Path(os.environ.get("USERPROFILE", "")) / "Apple" / "MobileSync" / "Backup",
    Path(os.environ.get("APPDATA", "")) / "Apple Computer" / "MobileSync" / "Backup",
]


def find_backup(given: Path | None) -> Path:
    """Verilen klasör bir yedekse onu, yedeklerin üst klasörüyse en yenisini döndürür."""
    roots = [given] if given else DEFAULT_ROOTS
    candidates = []
    for root in roots:
        if not root or not root.exists():
            continue
        if (root / "Manifest.plist").exists():
            return root
        candidates += [d for d in root.iterdir() if (d / "Manifest.plist").exists()]
    if not candidates:
        sys.exit("iPhone yedeği bulunamadı. Önce iTunes'ta 'Bu bilgisayar' seçili, şifresiz bir yedek al.")
    return max(candidates, key=lambda d: (d / "Manifest.plist").stat().st_mtime)


def connect_ro(path: Path) -> sqlite3.Connection:
    # immutable=1: yedek klasörüne -wal/-shm dosyası bile yazılmasın
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def find_plain_sms_db(backup: Path) -> Path:
    direct = backup / SMS_DB_HASH[:2] / SMS_DB_HASH
    if direct.exists():
        return direct
    con = connect_ro(backup / "Manifest.db")
    row = con.execute(
        "SELECT fileID FROM Files WHERE domain='HomeDomain' AND relativePath='Library/SMS/sms.db'"
    ).fetchone()
    con.close()
    if not row:
        sys.exit("Yedekte sms.db bulunamadı.")
    return backup / row[0][:2] / row[0]


@contextmanager
def sms_db(backup: Path):
    """sms.db yolunu verir. Şifreli yedekte parolayı sorar, sms.db'yi geçici klasöre çözer ve iş bitince siler."""
    with (backup / "Manifest.plist").open("rb") as f:
        encrypted = plistlib.load(f).get("IsEncrypted")
    if not encrypted:
        yield find_plain_sms_db(backup)
        return

    try:
        from iphone_backup_decrypt import EncryptedBackup, IncorrectPassphraseError, RelativePath
    except ImportError:
        sys.exit("Yedek şifreli. Çözmek için önce: pip install iphone_backup_decrypt")

    print("Yedek şifreli. Parolayı gir (yazarken ekranda görünmez, hiçbir yere kaydedilmez).")
    try:
        eb = EncryptedBackup(backup_directory=str(backup), passphrase=getpass.getpass("Yedek parolası: "))
        eb.test_decryption()
    except IncorrectPassphraseError:
        sys.exit("Parola yanlış.")
    except (KeyError, ValueError, FileNotFoundError) as e:
        sys.exit(f"Yedek okunamadı; yedekleme bitmemiş ya da yarım kalmış olabilir ({type(e).__name__}: {e}).")

    with tempfile.TemporaryDirectory(prefix="smsdb-") as tmp:
        path = Path(tmp) / "sms.db"
        eb.extract_file(relative_path=RelativePath.TEXT_MESSAGES, domain_like="HomeDomain", output_filename=str(path))
        del eb  # anahtarları ve geçici Manifest kopyasını bırak
        yield path


def decode_attributed_body(blob: bytes | None) -> str | None:
    """iOS 16+ bazı mesajların metnini sadece attributedBody (NSAttributedString) içinde tutar."""
    if not blob or b"NSString" not in blob:
        return None
    rest = blob.split(b"NSString", 1)[1][5:]  # sınıf başlığını atla
    if not rest:
        return None
    if rest[0] == 0x81:  # 2 baytlık uzunluk
        length, start = int.from_bytes(rest[1:3], "little"), 3
    else:
        length, start = rest[0], 1
    return rest[start : start + length].decode("utf-8", errors="ignore") or None


def apple_month(value) -> str:
    if not value:
        return ""
    seconds = value / 1e9 if value > 1e12 else value  # iOS 11+ nanosaniye tutar
    return (APPLE_EPOCH + timedelta(seconds=seconds)).strftime("%Y-%m")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--backup", type=Path, help="yedek klasörü (varsayılan: en yeni yedek)")
    parser.add_argument("--include-replied", action="store_true", help="cevap verdiğin kişilerin mesajlarını da al")
    parser.add_argument("--min-len", type=int, default=15)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    backup = find_backup(args.backup)
    print(f"Yedek: {backup.name}")

    with sms_db(backup) as db:
        con = connect_ro(db)
        cols = {r[1] for r in con.execute("PRAGMA table_info(message)")}
        body_col = "m.attributedBody" if "attributedBody" in cols else "NULL"
        rows = con.execute(
            f"""SELECT m.text, {body_col}, m.is_from_me, m.date, m.service, m.cache_roomnames, h.id
                FROM message m LEFT JOIN handle h ON m.handle_id = h.ROWID"""
        ).fetchall()
        con.close()

    replied = {sender for _, _, from_me, _, _, _, sender in rows if from_me and sender}

    stats = Counter()
    seen = set()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for text, body, from_me, date, service, room, sender in rows:
            stats["toplam"] += 1
            if from_me:
                stats["atlandi_giden"] += 1
                continue
            if room:
                stats["atlandi_grup"] += 1
                continue
            if sender in replied and not args.include_replied:
                stats["atlandi_cevaplanan_kisi"] += 1
                continue
            text = (text or decode_attributed_body(body) or "").replace("￼", "").strip()
            if len(text) < args.min_len:
                stats["atlandi_kisa_bos"] += 1
                continue

            masked, _ = mask_text(text)
            key = dedupe_key(masked)
            if key in seen:
                stats["atlandi_tekrar"] += 1
                continue
            seen.add(key)

            stype = sender_type(sender or "")
            record = {
                "id": make_id(masked),
                "text": masked,
                "sender": sender if stype == "alfanumerik" else stype,
                "sender_type": stype,
                "channel": "imessage" if service == "iMessage" else "sms",
                "source": "kendi_gelen_kutusu",
                "is_synthetic": False,
                "date": apple_month(date),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            stats["aday"] += 1

    print(f"{stats['aday']} aday mesaj → {out}")
    for k, v in stats.items():
        if k != "aday":
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
