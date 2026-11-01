"""Türkçe mesajlardaki kişisel verileri maskeler. Biçim korunur, değerler sıfırlanır.

Modül olarak:   from mask_pii import mask_text
CLI olarak:     python mask_pii.py girdi.jsonl|girdi.txt cikti.jsonl

.txt girdide her dolu satır bir mesajdır; dosyada tek başına '---' satırları varsa mesajlar onlarla
ayrılır (çok satırlı mesajlar için). .jsonl girdide her satırın "text" alanı maskelenir,
diğer alanlar korunur. id'si olmayan kayıtlara metinden türetilmiş bir id verilir.
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

UPPER = "A-ZÇĞİÖŞÜ"
LOWER = "a-zçğıöşü"

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
IBAN_RE = re.compile(r"\bTR\s?\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.IGNORECASE)
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
TCKN_RE = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")
# Alan kodu 2, 3, 4, 5 veya 8 (0850) ile başlayan 10 haneli numaralar. Önek (0 / +90) ya da ayraç
# şart: bitişik yazılmış 10 haneli takip numaraları telefon sanılmasın, LONG_DIGITS_RE onları sıfırlar.
PHONE_RE = re.compile(
    r"(?<![\d+])(?:(?:\+90[\s-]?|0)\(?[2-58]\d{2}\)?[\s-]?\d{3}|\(?[2-58]\d{2}\)?[\s-]\d{3})[\s-]?\d{2}[\s-]?\d{2}(?!\d)"
)
LONG_DIGITS_RE = re.compile(r"(?<!\d)\d{9,}(?!\d)")
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(/[^\s]*)", re.IGNORECASE)
NAME_WORD = rf"(?:[{UPPER}][{LOWER}]+|[{UPPER}]{{2,}})"
SALUTATION_RE = re.compile(rf"\b(Sayın|SAYIN|Sayin|SAYİN|Sn\.?|SN\.?)\s*({NAME_WORD}(?:\s+{NAME_WORD}){{0,3}})")
# Banka bildirimlerinde selamlamasız isimler: "Ali Veli alicisina", "... hesaptan Ali Veli adina".
# Küçük harfle yazılmış isimler de olur ("leyla yuksek alicisina"); kesme işaretinden sonraki ek ('da) isim sayılmaz.
NAME_ANY = rf"[{UPPER}{LOWER}]+"
RECIPIENT_RE = re.compile(rf"(?<![\w'’])((?:{NAME_ANY}\s+){{1,2}}{NAME_ANY})(\s+al[ıi]c[ıi]s[ıi]na)")
RECEIVER_RE = re.compile(
    rf"((?:gonderiniz|gönderiniz|gonderisi|gönderisi)\s+)((?:{NAME_ANY}\s+){{0,3}}{NAME_ANY})"
    rf"(\s+\((?:Gorevli|Görevli|Kendi|Komsu|Komşu|Diger|Diğer)\))"
)
ACCOUNT_HOLDER_RE = re.compile(rf"(hesaptan\s+)((?:{NAME_ANY}\s+){{0,3}}{NAME_ANY})(\s+ad[ıi]na)")
# Tireli hesap numaraları: "1234-12345678-123", "123 - 4567890"
ACCOUNT_RE = re.compile(r"(?<![\d-])\d{3,5}\s?-\s?\d{5,10}(?:\s?-\s?\d{2,4})?(?![\d-])")
PLATE_RE = re.compile(r"\b(?:0[1-9]|[1-7]\d|8[01])\s?([A-Z]{1,3})\s?\d{2,4}\b")
IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
IP_MASK = "0.0.0.0"
NOT_PLATE_LETTERS = {"GB", "MB", "KB", "TB", "TL", "DK", "SN", "GUN", "AY", "YIL", "KM", "KG", "AM", "PM"}

# Gelen kutusu sahibinin ve ailesinin isimleri her yerde maskelenir ("Merhaba AHMET", "Sevgili ...").
# private_names.txt: her satıra bir isim. Bu dosya asla yayınlanmaz.
PRIVATE_NAMES_FILE = Path(__file__).with_name("private_names.txt")
_FOLD = {"c": "cçCÇ", "g": "gğGĞ", "i": "iıIİ", "o": "oöOÖ", "s": "sşSŞ", "u": "uüUÜ"}


def _name_pattern(name: str) -> str:
    plain = name.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    return "".join(f"[{_FOLD.get(ch, ch + ch.upper())}]" for ch in plain)


def _load_private_names():
    if not PRIVATE_NAMES_FILE.exists():
        return None
    names = [n.strip() for n in PRIVATE_NAMES_FILE.read_text(encoding="utf-8").splitlines() if n.strip()]
    if not names:
        return None
    word = "(?:" + "|".join(_name_pattern(n) for n in sorted(names, key=len, reverse=True)) + ")"
    return re.compile(rf"(?<!\w){word}(?:\s+{word})*(?!\w)")


PRIVATE_NAMES_RE = _load_private_names()
GENERIC_SALUTATIONS = {
    "müşterimiz", "müşteri", "üyemiz", "üye", "kullanıcı", "kullanıcımız", "abonemiz", "abone",
    "yolcumuz", "veli", "velimiz", "hastamız", "ad", "öğrencimiz", "katılımcı",
}

PHONE_MASK = "0500 000 00 00"
IBAN_MASK = "TR00 0000 0000 0000 0000 0000 00"
CARD_MASK = "0000 0000 0000 0000"
TCKN_MASK = "00000000000"
EMAIL_MASK = "ornek@example.com"
NAME_MASK = "Ad Soyad"


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def tckn_ok(n: str) -> bool:
    d = [int(c) for c in n]
    if d[0] == 0:
        return False
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = sum(d[:10]) % 10
    return d[9] == d10 and d[10] == d11


def _zero_digits(s: str) -> str:
    return re.sub(r"\d", "0", s)


def _mask_url_path(path: str) -> str:
    """URL yolundaki kişiye özel görünen parçaları (rakam içeren uzun parçalar) 'xxxx' yapar."""
    def repl(m):
        seg = m.group(0)
        has_digit = any(c.isdigit() for c in seg)
        if (has_digit and len(seg) >= 8) or (seg.isdigit() and len(seg) >= 6):
            return "xxxx"
        return seg
    return re.sub(r"[A-Za-z0-9_-]+", repl, path)


def mask_text(text: str) -> tuple[str, Counter]:
    """Maskelenmiş metni ve neyin kaç kez maskelendiğini döndürür."""
    counts = Counter()

    def sub(pattern, fn, s, kind):
        def wrapper(m):
            out = fn(m)
            if out != m.group(0):
                counts[kind] += 1
            return out
        return pattern.sub(wrapper, s)

    text = sub(EMAIL_RE, lambda m: m.group(0) if m.group(0).endswith(("example.com", "example.org")) else EMAIL_MASK, text, "eposta")
    text = sub(IBAN_RE, lambda m: IBAN_MASK, text, "iban")

    def card(m):
        digits = re.sub(r"\D", "", m.group(0))
        return CARD_MASK if 13 <= len(digits) <= 19 and set(digits) != {"0"} and luhn_ok(digits) else m.group(0)
    text = sub(CARD_RE, card, text, "kart")

    text = sub(TCKN_RE, lambda m: TCKN_MASK if tckn_ok(m.group(0)) else m.group(0), text, "tckn")

    def phone(m):
        return m.group(0) if set(re.sub(r"\D", "", m.group(0))[-7:]) == {"0"} else PHONE_MASK
    text = sub(PHONE_RE, phone, text, "telefon")

    text = sub(URL_RE, lambda m: m.group(0)[: m.start(1) - m.start(0)] + _mask_url_path(m.group(1)), text, "url_yolu")
    text = sub(IP_RE, lambda m: IP_MASK, text, "ip")
    text = sub(ACCOUNT_RE, lambda m: _zero_digits(m.group(0)), text, "hesap_no")
    text = sub(LONG_DIGITS_RE, lambda m: _zero_digits(m.group(0)), text, "uzun_sayi")
    text = sub(
        PLATE_RE,
        lambda m: m.group(0) if m.group(1) in NOT_PLATE_LETTERS else re.sub(r"[A-Z]", "X", _zero_digits(m.group(0))),
        text,
        "plaka",
    )

    def name(m):
        if m.group(2).split()[0].lower() in GENERIC_SALUTATIONS or m.group(2) == NAME_MASK:
            return m.group(0)
        return f"{m.group(1)} {NAME_MASK}"
    text = sub(SALUTATION_RE, name, text, "isim")
    text = sub(RECIPIENT_RE, lambda m: m.group(0) if m.group(1) == NAME_MASK else NAME_MASK + m.group(2), text, "isim")
    text = sub(
        ACCOUNT_HOLDER_RE,
        lambda m: m.group(0) if m.group(2) == NAME_MASK else m.group(1) + NAME_MASK + m.group(3),
        text,
        "isim",
    )
    text = sub(
        RECEIVER_RE,
        lambda m: m.group(0) if m.group(2) == NAME_MASK else m.group(1) + NAME_MASK + m.group(3),
        text,
        "isim",
    )
    if PRIVATE_NAMES_RE:
        text = sub(PRIVATE_NAMES_RE, lambda m: NAME_MASK, text, "isim")

    return text, counts


def make_id(text: str, prefix: str = "r") -> str:
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}"


def main():
    if len(sys.argv) != 3:
        sys.exit("Kullanım: python mask_pii.py girdi.jsonl|girdi.txt cikti.jsonl")
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    sys.stdout.reconfigure(encoding="utf-8")

    if src.suffix == ".txt":
        lines = src.read_text(encoding="utf-8-sig").splitlines()
        if any(line.strip() == "---" for line in lines):
            # Çok satırlı mesajlar: mesajlar arasında tek başına '---' satırı
            blocks, current = [], []
            for line in lines + ["---"]:
                if line.strip() == "---":
                    if "".join(current).strip():
                        blocks.append("\n".join(current).strip())
                    current = []
                else:
                    current.append(line)
        else:
            blocks = [line.strip() for line in lines if line.strip()]
        records = [{"text": b, "source": "kendi_gelen_kutusu", "is_synthetic": False} for b in blocks]
    else:
        records = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]

    total = Counter()
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8") as f:
        for r in records:
            r["text"], counts = mask_text(r["text"])
            r.setdefault("id", make_id(r["text"]))
            total += counts
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"{len(records)} mesaj maskelendi → {dst}")
    for kind, n in total.most_common():
        print(f"  {kind}: {n}")
    print("Not: düz yazıdaki isim ve adresleri regex yakalayamaz, etiketlerken gözle kontrol et.")


if __name__ == "__main__":
    main()
