"""Şablon + otomatik varyasyonla sentetik Türkçe eğitim verisi üretir. Test setlerinden ayrıdır.

Kullanım:
    python gen_train.py data/train_synth.jsonl [--per-template 30] [--seed 13]

Her şablon {yuva} alanları içerir; yuvalar kurum adı, tutar, tarih, kod, alan adı gibi değerlerle
rastgele doldurulur. Mesajların bir kısmı SMS'lerdeki gibi Türkçe karaktersiz ya da büyük harfe çevrilir.
Doğrulama seti şablon bazında ayrılır (split=val): model ezber değil kalıp öğreniyor mu, onu ölçer.
"""
import argparse
import json
import random
import re
from pathlib import Path

from mask_pii import make_id

BANKS = {
    "Ziraat Bankası": "ziraatbank.com.tr", "Garanti BBVA": "garantibbva.com.tr", "Yapı Kredi": "yapikredi.com.tr",
    "Akbank": "akbank.com", "İş Bankası": "isbank.com.tr", "QNB": "qnb.com.tr", "DenizBank": "denizbank.com",
    "VakıfBank": "vakifbank.com.tr", "Halkbank": "halkbank.com.tr", "Enpara": "enpara.com", "TEB": "teb.com.tr",
    "ING": "ing.com.tr", "Kuveyt Türk": "kuveytturk.com.tr", "Papara": "papara.com",
}
CARGO = {
    "Yurtiçi Kargo": "yurticikargo.com", "Aras Kargo": "araskargo.com.tr", "MNG Kargo": "mngkargo.com.tr",
    "PTT Kargo": "ptt.gov.tr", "Sürat Kargo": "suratkargo.com.tr", "HepsiJET": "hepsijet.com",
    "Trendyol Express": "trendyol.com", "DHL": "dhl.com.tr", "UPS": "ups.com",
}
OPS = {"Turkcell": "turkcell.com.tr", "Vodafone": "vodafone.com.tr", "Türk Telekom": "turktelekom.com.tr"}
SHOPS = {
    "Trendyol": "trendyol.com", "Hepsiburada": "hepsiburada.com", "Amazon": "amazon.com.tr", "n11": "n11.com",
    "Getir": "getir.com", "Yemeksepeti": "yemeksepeti.com", "Migros": "migros.com.tr", "A101": "a101.com.tr",
    "LC Waikiki": "lcw.com", "MediaMarkt": "mediamarkt.com.tr", "Teknosa": "teknosa.com", "Pegasus": "flypgs.com",
    "obilet": "obilet.com", "Decathlon": "decathlon.com.tr", "Koton": "koton.com",
}
APPS = {
    "Steam": "steampowered.com", "Instagram": "instagram.com", "WhatsApp": "whatsapp.com", "Google": "google.com",
    "Apple": "apple.com", "Netflix": "netflix.com", "Spotify": "spotify.com", "Epic Games": "epicgames.com",
    "Discord": "discord.com", "Microsoft": "microsoft.com", "PlayStation": "playstation.com", "Binance TR": "binance.tr",
}
UTIL = {"BEDAŞ": "bedas.com.tr", "CK Boğaziçi": "ckbogazici.com.tr", "İGDAŞ": "igdas.istanbul", "İSKİ": "iski.istanbul",
        "Enerjisa": "enerjisa.com.tr", "AYEDAŞ": "ayedas.com.tr"}
GOV = {"e-Devlet": "turkiye.gov.tr", "GİB": "gib.gov.tr", "SGK": "sgk.gov.tr", "MHRS": "mhrs.gov.tr",
       "e-Nabız": "enabiz.gov.tr", "HGS": "hgs.gov.tr", "UYAP": "uyap.gov.tr", "KYK": "gsb.gov.tr"}
FAKE_WORDS = ["destek", "dogrula", "guvenlik", "online", "islem", "odeme", "iade", "takip", "sorgula", "hesap",
              "giris", "bilgi", "kampanya", "musteri", "tr", "onay", "merkez", "portal"]
FAKE_TLDS = [".com", ".net", ".org", ".info", ".xyz", ".online", ".site", ".live", ".top", "-tr.com", ".app"]
SHORTENERS = ["bit.ly", "t.ly", "cutt.ly", "tinyurl.com", "t2m.io", "kisa.link", "rb.gy"]
NAMES = ["Ahmet", "Mehmet", "Ayşe", "Fatma", "Emre", "Zeynep", "Mert", "Elif", "Burak", "Selin", "Can", "Deniz",
         "Hakan", "Esra", "Oğuz", "Merve", "Kerem", "İrem", "Serkan", "Gizem"]
RELATIVES = ["anne", "baba", "abla", "abi", "teyze", "dayı", "kanka", "kardeşim"]
GAMES = ["PUBG Mobile", "Valorant", "Free Fire", "Mobile Legends", "Roblox", "CS2", "Genshin Impact", "Fortnite"]
CITIES = ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Konya", "Samsun", "Eskişehir"]


def slug(name: str) -> str:
    t = name.lower().translate(str.maketrans("çğıöşüİ ", "cgiosui-"))
    return re.sub(r"[^a-z0-9-]", "", t).strip("-")


def fake_domain(brand: str, rng) -> str:
    base = slug(brand).replace("-", rng.choice(["", "-"]))
    if rng.random() < 0.25:  # harf değiştirme: steamcommunlty, garantlbbva
        i = rng.randrange(1, max(2, len(base) - 1))
        base = base[:i] + rng.choice("l1i0o") + base[i + 1:]
    word = rng.choice(FAKE_WORDS)
    return rng.choice([f"{base}-{word}", f"{word}-{base}", f"{base}{word}"]) + rng.choice(FAKE_TLDS)


def path(rng) -> str:
    return rng.choice(["", "/" + rng.choice(["giris", "tr", "dogrula", "odeme", "basvuru", "takip", "x"])])


def money(rng, lo=50, hi=25000) -> str:
    v = rng.uniform(lo, hi)
    if rng.random() < 0.5:
        return f"{int(v):,}".replace(",", ".") + " TL"
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


def fill(template: str, rng) -> str:
    kind = None
    vals = {}

    def pick(table):
        name = rng.choice(list(table))
        return name, table[name]

    for key, table in (("bank", BANKS), ("cargo", CARGO), ("op", OPS), ("shop", SHOPS), ("app", APPS),
                       ("util", UTIL), ("gov", GOV)):
        if "{" + key + "}" in template or "{" + key + "_" in template:
            name, dom = pick(table)
            vals[key] = name
            vals[f"{key}_real"] = dom
            vals[f"{key}_fake"] = fake_domain(name, rng) + path(rng)
            vals[f"{key}_up"] = name.upper().translate(str.maketrans("İÇĞÖŞÜ", "ICGOSU"))
            kind = key
    d, m = rng.randint(1, 28), rng.randint(1, 12)
    vals.update(
        amount=money(rng), small=money(rng, 0.5, 30), big=money(rng, 20000, 400000),
        date=f"{d:02d}.{m:02d}.2026", time=f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}",
        code4=f"{rng.randint(1000, 9999)}", code6=f"{rng.randint(100000, 999999)}",
        track="".join(rng.choice("0123456789") for _ in range(rng.choice([10, 12, 13, 14]))),
        last4=f"{rng.randint(1000, 9999)}", plate=f"{rng.randint(1, 81):02d} {''.join(rng.choice('ABCDEFGHJKLMNPRSTUVYZ') for _ in range(rng.choice([1, 2, 3])))} {rng.randint(10, 9999)}",
        name=rng.choice(NAMES), rel=rng.choice(RELATIVES), game=rng.choice(GAMES), city=rng.choice(CITIES),
        short=f"{rng.choice(SHORTENERS)}/{''.join(rng.choice('abcdefghkmnprstuvyz23456789') for _ in range(6))}",
        pct=f"%{rng.choice([10, 15, 20, 25, 30, 40, 50, 70])}", gb=f"{rng.choice([1, 2, 5, 10, 15, 20, 50])} GB",
        ref="".join(rng.choice("ABCDEFGHJKLMNPRSTUVYZ23456789") for _ in range(8)),
        mersis="MERSIS: 0000000000000000", ret=f"SMS almamak icin RET yazip {rng.choice([3525, 7889, 4946, 3347])}'e gonderin.",
        brand=rng.choice(list(SHOPS)), iban="TR00 0000 0000 0000 0000 0000 00", phone="0500 000 00 00",
        b=f"B0{rng.randint(1, 64):02d}",
    )
    text = template.format(**vals)
    return text


PERSONAL_PREFIXES = ["Sayın Ad Soyad, ", "Sn. Ad Soyad, ", "Merhaba Ad Soyad, ", "Ad Soyad, "]
PERSONAL_SUFFIXES = [
    " İşlem tarihi: {date} {time}.", " {last4} ile biten kartınız için geçerlidir.", " Referans no: {ref}.",
    " Kayıtlı adresiniz: {city}, {district} Mah. No: {no}.", " Araç: {plate}.", " Dosya no: {track}.",
    " Son işlem: {date} {time}, {amount}.",
]


def personalize(text: str, rng) -> str:
    """Sızan verilerle kişiselleştirilmiş dolandırıcılığı taklit eder: isim, kartın son 4 hanesi, tarih, adres,
    plaka. Bu ayrıntılar yalnızca gerçek kurum mesajlarında geçerse model "beni tanıyorsa gerçektir" diye öğrenir."""
    if rng.random() < 0.5 and not text.startswith(("Konu:", "Subject:")):
        text = rng.choice(PERSONAL_PREFIXES) + text[0].lower() + text[1:]
    suffix = rng.choice(PERSONAL_SUFFIXES).format(
        date=f"{rng.randint(1, 28):02d}.{rng.randint(1, 12):02d}.2026", time=f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}",
        last4=f"{rng.randint(1000, 9999)}", ref="".join(rng.choice("ABCDEFGHJKLMNPRSTUVYZ23456789") for _ in range(8)),
        city=rng.choice(CITIES), district=rng.choice(["Cumhuriyet", "Atatürk", "Yıldız", "Bahçelievler", "Fatih", "Yenimahalle"]),
        no=rng.randint(1, 120), plate=f"{rng.randint(1, 81):02d} {''.join(rng.choice('ABCDEFGHJKLMNPRSTUVYZ') for _ in range(rng.choice([1, 2, 3])))} {rng.randint(10, 9999)}",
        track="".join(rng.choice("0123456789") for _ in range(11)), amount=money(rng),
    )
    return text.rstrip() + suffix


def style(text: str, channel: str, rng) -> str:
    """SMS'lerin büyük kısmı Türkçe karaktersiz gelir; bazıları tamamen büyük harftir."""
    if channel == "sms" and rng.random() < 0.55:
        text = text.translate(str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU"))
    if channel == "sms" and rng.random() < 0.08:
        text = text.upper()
    return text


# (şablon id, etiket, kategori, kanal, şablon)
L, S, F = "legitimate", "spam", "fraud"
TEMPLATES = [
    # ---------------- Temiz: banka ----------------
    ("lb01", L, "banka", "sms", "{last4} ile biten kartinizla {date} {time}'de {brand} isyerinden {amount} harcama yapilmistir. Isleminiz size ait degilse {phone}'i arayiniz. {b}"),
    ("lb02", L, "banka", "sms", "Hesabinizdan {amount} tutarinda FAST islemi gerceklestirilmistir. Bilginiz disindaysa {bank} Musteri Iletisim Merkezi'ni arayiniz. {mersis} {b}"),
    ("lb03", L, "banka", "sms", "{bank}: Kredi karti ekstreniz olusmustur. Donem borcu {amount}, son odeme tarihi {date}. Odeme yaptiysaniz dikkate almayiniz. {b}"),
    ("lb04", L, "banka", "sms", "{bank} Mobil'e yeni bir cihazdan giris yapildi ({date} {time}). Bu islemi siz yapmadiysaniz hemen {phone} numarasini arayin. {b}"),
    ("lb05", L, "banka", "sms", "{bank} Internet Subesi giris sifreniz: {code6}. Sifre 3 dakika gecerlidir. {b}"),
    ("lb06", L, "banka", "sms", "Degerli musterimiz, {last4} ile biten kartiniz internet alisverislerine kapali oldugu icin isleminiz gerceklestirilemedi. Ayarlarinizi {bank} Mobil'den degistirebilirsiniz. {b}"),
    ("lb07", L, "banka", "sms", "Hesabiniza {name} tarafindan {amount} tutarinda havale gelmistir. Iyi gunler dileriz. {bank} {b}"),
    ("lb08", L, "banka", "eposta", "Konu: Hesap özetiniz hazır\nSayın Ad Soyad, {date} tarihli hesap özetiniz hazırlanmıştır. Detayları {bank_real} adresinden veya mobil uygulamadan görüntüleyebilirsiniz. Şifrenizi asla e-posta ile istemeyiz."),
    ("lb09", L, "banka", "sms", "{bank}: Asgari odeme tutari zamaninda odenmedigi icin kredi kartiniz gecici olarak alisverise kapatilmistir. Odeme sonrasi kartiniz otomatik olarak acilir. {b}"),
    ("lb10", L, "banka", "sms", "{bank}: Musteri tanima (KYC) bilgileriniz eksik. Eksik bilgiler tamamlanana kadar havale/EFT limitleriniz dusuk tutulacaktir. Tamamlamak icin en yakin subeyi ziyaret edin. {b}"),
    ("lb11", L, "banka", "sms", "{bank}: Ihtiyac kredisi talebiniz degerlendirilmis, su an icin onaylanamamistir. Ilerleyen donemde yeniden basvurabilirsiniz. {b}"),
    ("lb12", L, "banka", "sms", "EFT onayi: {amount} gonderim icin islem sifreniz {code6}. Bu sifre sadece sizin icindir, bankamiz cagri merkezi dahil kimse talep etmez. {bank} {b}"),
    # ---------------- Temiz: kargo ----------------
    ("lk01", L, "kargo", "sms", "{cargo}: {track} takip numarali gonderiniz dagitima cikmistir. Gonderinizi {cargo_real} uzerinden takip edebilirsiniz. {b}"),
    ("lk02", L, "kargo", "sms", "{cargo}: {track} gonderiniz alicisina ulasti. Hizmetimizi 1-5 arasi puanlamak icin {cargo_real} adresini ziyaret edebilirsiniz. {b}"),
    ("lk03", L, "kargo", "sms", "{shop} siparisiniz {cargo} ile yola cikti. Tahmini teslim tarihi {date}. Teslimat kodunuz: {code4}. Kodu yalnizca kuryeye soyleyiniz. {b}"),
    ("lk04", L, "kargo", "sms", "{cargo}: {track} numarali gonderiniz alici adresinde bulunamadiginiz icin subemize birakilmistir. 3 is gunu icinde teslim alabilirsiniz. {b}"),
    ("lk05", L, "kargo", "sms", "PTT: Yurt disi gonderiniz icin gumruk vergisi hesaplanmistir. Odemeyi e-Devlet'te PTT Gumruk Islemleri ekranindan yapabilirsiniz. {b}"),
    ("lk06", L, "kargo", "eposta", "Konu: Siparişin kargoya verildi\nMerhaba, {shop} siparişin {cargo} ile gönderildi. Takip numarası: {track}. Siparişlerim sayfasından takip edebilirsin: {shop_real}"),
    # ---------------- Temiz: operatör / fatura ----------------
    ("lo01", L, "operator_abonelik", "sms", "Paketinizdeki internetin %80'ini kullandiniz. Ek paket almak icin {op} uygulamasini kullanabilirsiniz. {b}"),
    ("lo02", L, "operator_abonelik", "sms", "{op}: {date} tarihli faturaniz {amount} olup son odeme tarihi {date}'dir. Detaylar {op_real} adresinde. {b}"),
    ("lo03", L, "operator_abonelik", "sms", "{gb} hediye internet paketiniz tanimlanmistir. Paketiniz 7 gun gecerlidir. {op} {b}"),
    ("lo04", L, "operator_abonelik", "sms", "Faturasiz hattiniza {amount} TL yukleme yapilmistir. Guncel bakiyenizi {op} uygulamasindan gorebilirsiniz. {b}"),
    ("lf01", L, "fatura", "sms", "{util}: {date} donemi faturaniz {amount} olup son odeme tarihi {date}'dir. Odeme yaptiysaniz dikkate almayiniz. {mersis} {b}"),
    ("lf02", L, "fatura", "sms", "{util}: {date} tarihinde {time} - {time} saatleri arasinda {city} bolgenizde planli bakim calismasi nedeniyle enerji kesintisi yapilacaktir. Detay: {util_real} {b}"),
    ("lf03", L, "fatura", "eposta", "Konu: Your invoice is available\nYour latest invoice for {amount} is ready. You can view and pay it from your account dashboard at {app_real}. Thank you for your business."),
    # ---------------- Temiz: devlet / sağlık ----------------
    ("ld01", L, "devlet", "sms", "e-Devlet: Adiniza yeni bir e-Tebligat gonderilmistir. Goruntulemek icin turkiye.gov.tr adresinden giris yapiniz. {b}"),
    ("ld02", L, "devlet", "sms", "HGS bakiyeniz yetersiz oldugu icin {date} tarihli kopru gecisiniz ihlalli olarak kaydedildi. Gecis bedelini cezasiz odemek icin son tarih {date}. Bakiye yukleme: HGS uygulamasi. {b}"),
    ("ld03", L, "devlet", "sms", "{date} tarihli {time} randevunuz Göz Hastalıkları polikliniğine kaydedilmiştir. Randevu saatinden 15 dakika önce hastanede olunuz. Sağlık Bakanlığı"),
    ("ld04", L, "devlet", "sms", "e-Nabiz: {date} tarihli tahlil sonuclariniz sisteme yuklenmistir. Sonuclarinizi e-Nabiz uygulamasindan gorebilirsiniz."),
    ("ld05", L, "devlet", "sms", "Turkiye.gov.tr giris icin tek kullanimlik sifreniz {code6}. Bu sifreyi siz istemediyseniz dikkate almayiniz."),
    ("ld06", L, "devlet", "sms", "GIB: {date} tarihli e-Arsiv faturaniz olusturulmustur. Faturaniza dijital.gib.gov.tr adresinden ulasabilirsiniz. {b}"),
    ("ld07", L, "devlet", "sms", "AFAD: Bagislarinizi yalnizca afad.gov.tr/bagis adresinden veya resmi banka hesaplarimizdan yapiniz. Kisisel hesaplara yapilan bagis cagrilarina itibar etmeyiniz."),
    # ---------------- Temiz: OTP / hesap ----------------
    ("lt01", L, "otp_kod", "sms", "{shop} uyeliginizi tamamlamak icin onay kodunuz {code4}. Iyi alisverisler!"),
    ("lt02", L, "otp_kod", "sms", "{app} hesabınıza giriş için onay kodu {code6}. Kod 5 dakika geçerlidir."),
    ("lt03", L, "otp_kod", "sms", "Your {app} verification code is {code6}. Don't share this code with anyone."),
    ("lt04", L, "otp_kod", "eposta", "Konu: Güvenlik kodun\nMerhaba Ad Soyad, {app} hesabın için şifre sıfırlama isteği aldık. Kodun: {code6}. Bu talebi sen yapmadıysan bu e-postayı yok sayabilirsin."),
    ("lt05", L, "otp_kod", "eposta", "Konu: Yeni bir cihazdan giriş yapıldı\n{app} hesabına {date} {time}'de {city}, TR konumundan yeni bir cihazla giriş yapıldı. Bu sen değilsen şifreni {app_real} üzerinden değiştir."),
    ("lt06", L, "otp_kod", "eposta", "Subject: New sign-in to your {app} account\nWe noticed a new sign-in from {city}, Turkey on {date}. If this was you, no action is needed. If not, change your password at {app_real}."),
    ("lt07", L, "otp_kod", "sms", "Odemenizi onaylamak icin {code4} kodunu giriniz. {brand} {amount}. Kodu kimseyle paylasmayiniz. {b}"),
    ("ls01", L, "sosyal_medya", "eposta", "Konu: Şifren değiştirildi\nMerhaba, {app} hesabının şifresi kısa süre önce değiştirildi. Bu değişikliği sen yaptıysan bir şey yapmana gerek yok."),
    # ---------------- Temiz: alışveriş / sohbet ----------------
    ("la01", L, "ilan_alisveris", "sms", "{shop}: Iade talebiniz onaylandi. {amount} tutarindaki iadeniz 3-7 is gunu icinde kartiniza yansiyacaktir. {b}"),
    ("la02", L, "ilan_alisveris", "eposta", "Konu: Siparişin alındı\nTeşekkürler! {amount} tutarındaki siparişin alındı. Sipariş no: {ref}. Siparişlerim sayfasından takip edebilirsin."),
    ("lc01", L, "sohbet", "whatsapp", "{name} yarın 8'de buluşuyoruz değil mi, ben biraz geç kalabilirim"),
    ("lc02", L, "tanidik", "whatsapp", "{rel} geçen haftaki konserin biletini ben almıştım, kişi başı {amount} düşüyor. Acelesi yok, maaş yatınca gönderirsin 🙂"),
    ("lc03", L, "tanidik", "whatsapp", "{rel} bu benim yeni numaram, eskisini iş yerine verdim. Kaydedersin, akşam ararım."),
    ("lc04", L, "sohbet", "whatsapp", "Selam {name}, toplantı notlarını mail attım, bakınca dönüş yaparsın"),
    ("lc05", L, "is_ilani", "eposta", "Konu: Mülakat daveti\nMerhaba Ad Soyad, başvurunuz için teşekkür ederiz. {date} tarihinde {time}'de online görüşmeye davet etmek isteriz. Uygun değilseniz kariyer portalımızdan yeni saat seçebilirsiniz."),
    # ---------------- Spam (gerçek şirket reklamı) ----------------
    ("sp01", S, "kampanya", "sms", "{shop}'da {pct} indirim basladi! Secili urunlerde {amount} ve uzeri alisverise ek indirim. {shop_real} {ret} {b}"),
    ("sp02", S, "kampanya", "sms", "Size ozel {amount} indirim kuponu hesabinizda! Kod: {ref}. Son gun {date}. {short} {ret}"),
    # ---- v2: dev hata analizinden çıkan mesaj türleri (test yarısına bakılmadan) ----
    ("lb13", L, "banka", "sms", "{shop} alisveris kredin kapsaminda {date} tarihli {ref} numarali siparisinin {code4[0]}. taksidi olan {amount} tahsil edildi. Kalan taksitlerini uygulamadan gorebilirsin. {b}"),
    ("lb14", L, "banka", "sms", "{date} tarihinde {shop} uzerinden verdigin siparisin icin {amount} odeme {last4} ile biten kartindan alinmistir. Odeme detaylari: {short} {b}"),
    ("lb15", L, "banka", "sms", "{bank_up} ARACILIGIYLA SATIN ALDIGINIZ {amount} TUTARINDAKI {track} NOLU KONUT SIGORTASI POLICENIZ DUZENLENMISTIR. POLICENIZE MOBIL UYGULAMADAN ULASABILIRSINIZ. {b}"),
    ("lb16", L, "banka", "sms", "Kredi basvurunuza devam etmek icin kimlik dogrulama adimini tamamlayin: {bank_real}/basvuru. Basvurunuz 7 gun icinde tamamlanmazsa iptal edilir. {b}"),
    ("lb17", L, "banka", "sms", "Tebrikler, artik {bank} musterisisiniz! Hesabinizi {bank} Mobil uzerinden hemen kullanmaya baslayabilirsiniz. Musteri Hizmetleri: {phone} {mersis} {b}"),
    ("lb18", L, "yatirim", "sms", "{bank} Yatirim: {date} tarihinde resmi tatil nedeniyle Borsa Istanbul'da islem yapilmayacaktir. Bilgilerinize sunariz. {b}"),
    ("lk07", L, "kargo", "sms", "Degerli musterimiz {shop} tarafindan gonderilen {track} takip numarali kargonuz teslim edilmistir. Hizmetimizi degerlendirmek icin {short} {cargo} {b}"),
    ("lk08", L, "kargo", "sms", "{shop} tarafindan gonderilen {track} numarali kargonuz dagitima cikmistir. {code4} numarali teslimat kodu ile temassiz teslim alabilirsiniz. Takip: {short} {b}"),
    ("ld08", L, "devlet", "sms", "{plate} araciniz ile {date} {time}'de Kuzey Marmara Otoyolu gisesinden odemesiz gecilmistir. Ucret 15 gun icinde odenmezse 4 kati ceza eklenecek, odenmeyen tutarlar icin icra takibi baslatilacaktir. Odeme: hgs.gov.tr {mersis} {b}"),
    ("ld09", L, "devlet", "sms", "SBM: {plate} plakali araciniza ait kasko ve trafik sigortasi kayit bilgileri talebiniz uzerine asagida yer almaktadir. YASAL UYARI: Bu bilgiler sigorta sirketlerinden alinan kayitlardir. Detay: sbm.org.tr {b}"),
    ("lo05", L, "operator_abonelik", "sms", "{date} tarihli faturanizin odenmemesi nedeniyle kapatilan hattiniz odemeniz sonrasi yeniden acilmistir. Hat acma ucreti {amount} faturaniza yansitilacaktir. {op} {b}"),
    ("lo06", L, "operator_abonelik", "sms", "Paketinizdeki internetin tamami kullanildi. Akilli Fatura kapsaminda {gb} hediye kullaniminiz basladi. Ek paket icin EK yazip 2222'ye gonderebilirsiniz, {amount}. {b}"),
    ("lf04", L, "fatura", "sms", "{util}: {track} numarali ariza/kesinti basvurunuz alinmistir. Basvurunuzun durumunu {short} adresinden sorgulayabilirsiniz. {mersis} {b}"),
    ("la03", L, "diger", "sms", "Degerli musterimiz, {date} tarihinde {brand} magazamizdan yaptiginiz alisverisi degerlendirmek icin 1 dakikalik anketimize katilir misiniz? {short} {ret} {b}"),
    ("la04", L, "diger", "sms", "{shop} uygulamasi guncellendi! Siparislerinizi artik daha kolay takip edebilirsiniz. Bilgi icin: {short} {b}"),
    ("sp13", S, "kampanya", "sms", "{brand} icin {amount} kuponun hesabinda! Sinirli sure gecerli, sana ozel hediye. Simdi al, pesin fiyatina taksitle ode: {short} {ret} {mersis} {b}"),
    ("sp14", S, "kampanya", "sms", "Karsilikli {amount} hediye puan kazanalim! Arkadasina davet linkini gonder, ikiniz de kazanin :) {short} {ret} {mersis} {b}"),
    ("sp15", S, "kampanya", "sms", "Puanlarinin suresi {code4[0]} gun sonra doluyor! {amount} degerindeki puanlarini kaybetmeden {shop} uygulamasindan kullan: {short} {ret} {b}"),
    ("sp16", S, "yatirim", "sms", "{bank} Kripto'da ilk isleminize ozel {amount} odul kazanabilirsiniz! Kampanya {date}'e kadar gecerli. Detay: {bank_real}/kampanyalar {ret} {mersis} {b}"),
    ("sp17", S, "ilan_alisveris", "sms", "Aracinizin degerini hesapladiginizi gorduk! Aracinizi ayni gun nakde cevirmek icin ucretsiz ekspertiz randevusu olusturun: {short} {ret} {mersis} {b}"),
    ("sp18", S, "kampanya", "sms", "Ilk ay sadece 1 TL! Telefon, tablet ve bilgisayarlarda 6 ay ve uzeri kiralamada efsane firsat. Kacirma: {short} Ret: www.iys.tc/{ref} {b}"),
    ("sp03", S, "banka", "sms", "{bank}'tan size ozel {big}'ye varan ihtiyac kredisi! Hemen basvurun: {bank_real} {ret} {mersis} {b}"),
    ("sp04", S, "banka", "sms", "Kredi kartinizla {brand}'dan yapacaginiz {amount} ve uzeri alisverise {pct} bonus! Kampanyaya katilmak icin {bank} Mobil. {ret} {b}"),
    ("sp05", S, "operator_abonelik", "sms", "{op}'a ozel firsat! {gb} internet sadece {amount}. Hemen almak icin {op} uygulamasina girin. {ret}"),
    ("sp06", S, "kampanya", "eposta", "Konu: Bu fırsat kaçmaz! 🎉\n{shop}'da hafta sonuna özel {pct} indirim. Favorilerini sepete ekle, fırsatı kaçırma. Üyelikten ayrılmak için tıkla."),
    ("sp07", S, "kampanya", "sms", "{brand} magazalarinda {date}'e kadar 2. urune {pct} indirim! Detaylar magazalarimizda. {ret} {mersis}"),
    ("sp08", S, "oyun", "eposta", "Konu: Yeni sezon başladı!\n{game} yeni sezonda seni bekliyor. Sınırlı süreli paketleri kaçırma, hemen oyuna gir!"),
    ("sp09", S, "kampanya", "sms", "Arkadasini davet et, ikiniz de {amount} kazanin! Davet kodun: {ref}. {shop} {ret}"),
    ("sp10", S, "kampanya", "eposta", "Subject: {pct} off this weekend only\nDon't miss our biggest sale of the season. Shop now at {shop_real}. Unsubscribe anytime."),
    ("sp11", S, "bahis", "sms", "Misli'de bu aksam derbiye ozel oranlar! Kuponunu olustur, kazancini katla. misli.com {ret} {mersis}"),
    ("sp12", S, "yatirim", "sms", "{bank} Yatirim: Hisse senedi alim satimlarinizda {date}'e kadar komisyonsuz islem firsati! Detay: {bank_real} {ret}"),
    # ---------------- Dolandırıcılık: linkli kurum taklidi ----------------
    ("fb01", F, "banka", "sms", "{bank}: Hesabiniz guvenlik nedeniyle gecici olarak askiya alinmistir. 24 saat icinde dogrulama yapmazsaniz hesabiniz kapatilacaktir: {bank_fake}"),
    ("fb02", F, "banka", "sms", "Degerli musterimiz, {amount} tutarinda supheli islem tespit edildi. Islemi iptal etmek icin: {bank_fake}"),
    ("fb03", F, "banka", "sms", "{bank_up}: Kart limitiniz {big}'ye yukseltilmeye uygundur. Onay icin kart bilgilerinizi dogrulayin: {short}"),
    ("fb04", F, "banka", "sms", "Tebrikler, {big} tutarinda konut disi ihtiyac finansmani basvurunuz on onay aldi. Sigorta ve ekspertiz bedeli {amount} yatirildiktan sonra kullandirim yapilacaktir. Detay icin {phone}"),
    ("fk01", F, "kargo", "sms", "{cargo}: Paketiniz agirlik farki nedeniyle ek {small} kargo bedeli bekliyor. Bugun odenmezse gonderi cikis subesine geri doner. Odeme: {cargo_fake}"),
    ("fk02", F, "kargo", "sms", "{cargo}: {track} numarali paketiniz icin teslimat denemesi basarisiz oldu. Yeni randevu: {cargo_fake}"),
    ("fk03", F, "kargo", "sms", "Gumrukte bekleyen paketiniz icin {small} vergi odemesi gerekmektedir. Odeme yapilmazsa paket imha edilecektir: {short}"),
    ("fk04", F, "kargo", "sms", "Your {cargo} package is on hold due to an unpaid shipping fee of $1.99. Pay within 24h to avoid return: {cargo_fake}"),
    ("fd01", F, "devlet", "sms", "{gov}: Adiniza {amount} tutarinda odenmemis ceza bulunmaktadir. 15 gun icinde odemelerde %25 indirim: {gov_fake}"),
    ("fd02", F, "devlet", "sms", "{plate} plakali araciniz icin ihlalli gecis cezasi kesilmistir. 10 kat ceza uygulanmamasi icin hemen odeyin: {gov_fake}"),
    ("fd03", F, "devlet", "sms", "{gov}: {amount} vergi iadeniz bulunmaktadir. Iadenin aktarilmasi icin kart bilgilerinizi dogrulayiniz: {gov_fake}"),
    ("fd04", F, "devlet", "sms", "Cihaz kayit uyarisi: Telefonunuz yurt disindan getirilmis ve harci odenmemis gorunuyor. Sebekeden cikarilmamak icin kayit ucreti {amount} odemeniz gerekir: {gov_fake}"),
    ("fd05", F, "devlet", "sms", "SGK: Emekli ikramiyeniz {amount} olarak hesaplanmistir. Odemenin yapilmasi icin bilgilerinizi guncelleyiniz: {gov_fake}"),
    ("fd06", F, "saglik", "sms", "MHRS: Randevu kaydinizda kimlik dogrulamasi eksik. Randevunuz {date} tarihinde otomatik silinecektir. Hemen tamamlayin: {gov_fake}"),
    ("fo01", F, "operator_abonelik", "sms", "{op}: Hattiniza tanimli {gb} hediye paketin suresi bugun doluyor. Kullanmak icin giris yapin: {op_fake}"),
    ("fo02", F, "operator_abonelik", "eposta", "Konu: Hesabınız beklemeye alındı\n{app} üyeliğiniz için son tahsilat başarısız oldu. İçeriklerinize erişiminiz kısıtlandı. Kartınızı yeniden tanımlamak için: {app_fake}"),
    ("fo03", F, "operator_abonelik", "sms", "{util}: Sayacinizda usulsuz kullanim tespit edildi. Hakkinizda cezai islem baslatilmadan once 24 saat icinde {amount} tespit bedelini odeyin: {util_fake}"),
    ("ft01", F, "otp_kod", "eposta", "Konu: Hesabınız kilitlendi\n{app} hesabınız güvenlik nedeniyle kilitlendi. 24 saat içinde doğrulamazsanız hesabınız ve verileriniz kalıcı olarak silinir: {app_fake}"),
    ("ft02", F, "sosyal_medya", "sosyal_medya", "Meta Business: Sayfanız topluluk kurallarını ihlal ettiği gerekçesiyle yayından kaldırılacak. Karar hatalıysa 12 saat içinde itiraz edin: {app_fake}"),
    ("ft03", F, "sosyal_medya", "sosyal_medya", "Tebrikler! Hesabınız mavi tik doğrulaması için seçildi ✅ Başvurunuzu 24 saat içinde tamamlayın: {app_fake}"),
    ("ft04", F, "otp_kod", "eposta", "Subject: Unusual sign-in activity\nWe detected a sign-in to your {app} account from an unknown device. Verify your identity within 24 hours or your account will be suspended: {app_fake}"),
    ("fa01", F, "ilan_alisveris", "eposta", "Konu: İade işleminiz tamamlanamadı\n{amount} tutarındaki iadeniz kart doğrulaması yapılamadığı için beklemede. İadenizin yansıması için: {shop_fake}"),
    ("fa02", F, "odul_cekilis", "sms", "{shop} yil donumu: kisa anketi dolduran ilk 500 kisiye {amount} hediye ceki! Anket 2 dakika: {shop_fake}"),
    ("fa03", F, "odul_cekilis", "sms", "Tebrikler! {shop} cekilisinde {big} degerinde odul kazandiniz. Odulunuzu 24 saat icinde talep edin: {short}"),
    ("fg01", F, "oyun", "sms", "{game} etkinligi: hesabina bedava oyun parasi tanimlandi! Almak icin oyun hesabinla giris yap: {short}"),
    ("fg02", F, "oyun", "sosyal_medya", "{game} oyuncularına özel: sınırlı sayıda ücretsiz skin kodu dağıtıyoruz 🎮 Kodunu almak için oyun hesabınla eşleştir: {app_fake}"),
    ("fg03", F, "oyun", "eposta", "Konu: Ödemeniz başarısız\n{game} için yaptığınız {amount} yükleme işlemi tamamlanamadı. Bakiyeniz bloke edildi; iadenin yapılabilmesi için kart bilgilerinizi şu sayfada onaylayın: {shop_fake}"),
    ("fy01", F, "yatirim", "eposta", "Konu: Cüzdanınız senkronize edilmedi\n{app} hesabınızda bekleyen 0,15 BTC çekiminiz var. Çekimin tamamlanması için cüzdan kurtarma kelimelerinizi doğrulayın: {app_fake}"),
    ("fz01", F, "bahis", "sms", "{amount} DENEME BONUSU HESABINDA! Yatirim sartsiz, cevrimsiz, aninda cekim. Hemen uye ol: {short}"),
    ("fz02", F, "bahis", "sms", "Hos geldin bonusu {pct}! Ilk yatirimina {amount} ekstra, kayip bonusu ve freespin seni bekliyor: {short}"),
    # ---- Kamu uyarılarında bildirilen kalıplar (kaynaklar: data/external/public_warning_patterns.jsonl) ----
    ("fp01", F, "devlet", "sms", "KGM: {plate} plakali aracinizin odenmemis HGS gecis borcu bulunmaktadir. Borcunuz {date} tarihine kadar odenmezse icra islemi baslatilacaktir: {gov_fake}"),
    ("fp02", F, "devlet", "sms", "SGK: {amount} GSS prim borcunuz bulunmaktadir. Odeme yapilmazsa banka hesaplariniza bloke konulacaktir. Borc sorgulama: {gov_fake}"),
    ("fp03", F, "devlet", "sms", "Emeklilerimize mujde! Maasiniza {amount} ek zam yapildi. Farki hesabiniza almak icin e-Devlet uzerinden basvurunuzu tamamlayin: {gov_fake}"),
    ("fp04", F, "devlet", "sms", "Yenievim: Sosyal konut kampanyasi on basvurulari basladi. Kura listesine girmek icin e-Devlet bilgilerinizle basvurun, son gun {date}: {gov_fake}"),
    ("fp05", F, "devlet", "sms", "Sayin Ad Soyad, adiniza noterden ihtarname duzenlenmis ve mahkemede dosya acilmistir. Belgeyi goruntulemek icin e-Tebligat adresinize giris yapin: {gov_fake}"),
    ("fp06", F, "devlet", "sms", "EDS kamera kaydiyla tespit edilen trafik para cezaniz ({amount}) sisteme yansitilmistir. %25 indirimden yararlanmak icin son 24 saatiniz kaldi: {gov_fake}"),
    ("fp07", F, "devlet", "sms", "{city} Belediyesi: e-Devlet Kapisi sifreniz ile hesabiniza giris yapilmistir. Size ait degilse lutfen kontrol ediniz: {gov_fake}"),
    # ---- Kullanıcının Şikâyetvar'da bulduğu anlatımlardan çıkan kalıplar (metin alıntılanmadı) ----
    ("fw01", F, "odul_cekilis", "sosyal_medya", "Merhaba 🎉 Çekilişimizi kazanan şanslı takipçimiz sizsiniz! Ödülünüzü teslim alabilmek için profilimizdeki linkten kod girişi yapıp canlı desteğe bağlanın."),
    ("fw02", F, "odul_cekilis", "whatsapp", "Ödülünüz paketlendi ✅ Kargoya verilebilmesi için {small} kargo ve sigorta bedelini aşağıdaki hesaba göndermeniz gerekiyor. Alıcı adı açıklamaya yazılmalıdır. {iban}"),
    ("fw03", F, "odul_cekilis", "whatsapp", "Ödülünüzün değeri yüksek olduğu için yasal olarak {amount} ÖTV ödenmesi gerekiyor. Ödeme yapılmadan ürün gümrükten çıkamaz. Ödeme sonrası kargo takip numaranız iletilecektir."),
    ("fw04", F, "odul_cekilis", "whatsapp", "Ödülü kabul edip sözleşmeyi onayladığınız için vazgeçme hakkınız bulunmamaktadır. Ödeme yapılmazsa {big} cayma bedeli e-Devlet hesabınıza borç olarak yansıtılacak ve IMEI numaranız üzerinden işlem başlatılacaktır."),
    ("fw05", F, "ilan_alisveris", "whatsapp", "Siparişiniz alındı 😊 Stoklar sınırlı olduğu için ödemeyi bugün havale ile yapmanız gerekiyor. Firmamızın ödemeleri muhasebe sorumlumuz adına kayıtlı hesaptan alınıyor: {iban} Açıklamaya sipariş numaranızı yazın."),
    ("fw06", F, "ilan_alisveris", "sosyal_medya", "🔥 Resmi distribütör sezon sonu: {brand} ürünlerinde %40-60 indirim! Sadece bugün geçerli, stoklar tükenmeden sipariş verin 👉 {shop_fake}"),
    ("fw07", F, "ilan_alisveris", "eposta", "Konu: Siparişiniz onaylandı - %40 indirim uygulandı\n{brand} resmi mağazasından verdiğiniz siparişin ödemesi alındı. Kargo bilgileriniz 7-10 iş günü içinde iletilecektir. Sipariş takibi: {shop_fake}"),
    ("fw08", F, "is_ilani", "telegram", "Hoş geldiniz! Referans kodunuz onaylandı. Görevi basit: otel rezervasyonlarını sistem üzerinden tamamlıyorsunuz, günlük 60 sipariş = {amount} komisyon. Siparişleri tamamlamak için hesabınıza USDT yüklemeniz gerekiyor, gün sonunda komisyonla birlikte iade edilir."),
    ("fw09", F, "is_ilani", "telegram", "Tebrikler, özel kombine siparişe denk geldiniz! Bu sipariş 3 kat komisyon kazandırır. Devam edebilmek için hesabınızdaki eksi bakiyeyi {amount} yükleyerek kapatmanız gerekiyor, aksi halde birikmiş kazancınız çekilemez."),
    ("fw10", F, "yatirim", "telegram", "Hesabınızda {big} kazanç birikti 🎉 Çekim yapabilmeniz için son bir doğrulama ödemesi olarak {amount} yatırmanız gerekiyor. Bu ödemeyi yapmazsanız önceki yatırımlarınız da sistemde bloke kalır."),
    ("fw11", F, "yatirim", "whatsapp", "Yatırım danışmanınız olarak söylüyorum, şu an çok kritik bir fırsat var. {amount} daha eklerseniz toplam bakiyenizi bugün hepsiyle birlikte çekebileceksiniz. Fırsat akşam 18:00'de kapanıyor."),
    ("fw12", F, "ilan_alisveris", "whatsapp", "Merhaba, rezervasyonunuz için teşekkürler 🚗 Sistemimizde şu an kredi kartı ile ödeme alınamıyor, kiralama bedeli ve depozito olarak toplam {amount} tutarını şirket muhasebemize ait hesaba göndermeniz yeterli: {iban} Dekontu bu numaraya iletin."),
    ("fw13", F, "ilan_alisveris", "whatsapp", "Aracınız teslime hazır ✅ Sözleşmenin düzenlenebilmesi için ehliyetinizin ön ve arka yüzünün fotoğrafını ve kimlik bilgilerinizi bu numaraya göndermeniz gerekiyor. Ödemenin kalan kısmı için ikinci hesap: {iban}"),
    ("fw14", F, "ilan_alisveris", "whatsapp", "Merhaba, kiralama şirketimizin anlaşmalı sigortasından arıyorum. Aracınızın kaskosu için {big} teminat bedeli muhasebe kaydına girmesi gerekiyor, 15 dakika içinde aynı hesabınıza iade edilecek. Hesap bilgisi: {iban}"),
    ("fw15", F, "diger", "sms", "Sayin Ad Soyad, gecmise donuk trafik kazasi kaydiniz nedeniyle sigorta sirketinde adiniza {amount} tazminat alacagi bulunmaktadir. Odemenin yapilmasi icin hukuk buromuz araciligiyla vekalet islemi gerekmektedir. Bilgi: {phone}"),
    ("fw16", F, "devlet", "whatsapp", "Sayın Ad Soyad, {city} hukuk bürosundan yazıyoruz. Geçirdiğiniz trafik kazasında ehliyetsiz araç kullandığınız tespit edilmiştir. {amount} ödeme yapılmaması halinde hakkınızda icra takibi başlatılacaktır. Bugün dönüş yapmanızı rica ederiz."),
    ("fw17", F, "banka", "sms", "{bank}: Kredi karti sigorta iadeniz {amount} olarak onaylanmistir. Iadenin kartiniza yapilmasi icin musteri temsilcimiz sizi arayacaktir, kart bilgilerinizi temsilcimize teyit ediniz."),
    ("fw18", F, "ilan_alisveris", "eposta", "Konu: Siparişiniz hazırlanıyor\n{amount} tutarındaki siparişiniz için teşekkür ederiz. Yoğunluk nedeniyle kargolama süresi 10-15 iş günüdür. Siparişinizle ilgili tüm sorularınız için yalnızca WhatsApp destek hattımızdan iletişime geçebilirsiniz."),
    ("fw19", F, "is_ilani", "whatsapp", "Merhaba, kariyer sitesindeki başvurunuz olumlu değerlendirildi 🎉 Müşteri temsilcisi pozisyonu, aylık {amount} maaş. Eğitim sürecine başlamak için başvuru formunu doldurun ve IBAN bilginizi iletin, personel giriş işlemleri için hesabınıza test ödemesi yapılacak."),
    ("fw20", F, "is_ilani", "whatsapp", "Personel giriş işleminiz için hesabınıza {small} gönderildi. Muhasebe kaydının tamamlanması için bu tutarı hemen aşağıdaki hesaba aktarıp dekontu bu numaraya gönderin: {iban}"),
    ("fw21", F, "is_ilani", "whatsapp", "Merhaba! {shop} bünyesinde yarı zamanlı online iş imkânı 🛍️ Telefonundan günde 1-2 saat ayırarak günlük {amount} kazanabilirsin. Detaylar ve kayıt için Telegram grubumuza katıl: t.me/{ref}"),
    ("fw22", F, "is_ilani", "whatsapp", "Merhaba, {op} çağrı merkezi personel alımı için ön görüşmeniz olumlu geçti. İş başvurunuzu e-Devlet üzerinden tamamlamamız gerekiyor; sizi şimdi arayacağım, ekran paylaşımını açıp adımları birlikte yapalım."),
    ("fw23", F, "is_ilani", "sosyal_medya", "📞 Kurumsal çağrı merkezimize evden çalışacak personel alınıyor! Deneyim şartı yok, haftalık ödeme. Başvuru formu: {shop_fake} Başvuru sonrası maaş hesabınızın açılması için temsilcimiz sizi yönlendirecektir."),
    ("fw24", F, "diger", "whatsapp", "Uluslararası Sertifika Programı kaydınız oluşturuldu. Sertifika ücreti {amount}'dir. Kayıt sözleşmesini onayladığınız için ödeme yapılmaması halinde bedelin 3 katı tutarında cezai şart uygulanacaktır."),
    ("fw25", F, "odul_cekilis", "whatsapp", "DHL Express: Adınıza yurt dışından 950.000 EUR değerinde bağış paketi gönderilmiştir. Paketin teslim edilebilmesi için açık adresinizi, kimlik fotoğrafınızı ve {small} gümrük işlem ücretini iletmeniz gerekmektedir."),
    ("fw26", F, "devlet", "whatsapp", "Merhaba, {city} Sosyal Hizmetler biriminden yazıyoruz. e-Devlet üzerinden yaptığınız kırtasiye yardımı başvurunuz onaylandı. Yardımın yatırılması için kira sözleşmenizin ve son kira dekontunuzun fotoğrafını bu numaraya gönderiniz."),
    ("fw27", F, "diger", "sms", "Selamun aleykum Sayin Ad Soyad, daha once yetim cocuklarimiza destek olmustunuz, Allah razi olsun. Kis yardimi kampanyamiz icin tekrar destek olmak isterseniz bagis hesabimiz: {iban} Vakfimiz adina temsilcimiz sizi arayacaktir."),
    ("fw28", F, "devlet", "sms", "Sosyal Yardimlasma ve Dayanisma Vakfi: Engelli bakici maasinizla ilgili islem yapilacaktir. Odemenin kesilmemesi icin IBAN ve banka bilgilerinizi bugun {phone} numarasina iletiniz."),
    ("lr05", L, "devlet", "sms", "SYDV: {date} donemine ait sosyal yardim odemeniz {amount} olarak PTT subelerinden veya banka hesabiniza yatirilmistir. Bilgi icin ALO 144. {b}"),
    ("lr06", L, "is_ilani", "eposta", "Konu: Başvurunuz alındı\nMerhaba Ad Soyad, müşteri temsilcisi pozisyonuna başvurunuz için teşekkür ederiz. Başvurunuz insan kaynakları ekibimiz tarafından değerlendirilecek. Sürecin hiçbir aşamasında sizden ücret, banka bilgisi veya e-Devlet şifresi talep etmeyiz."),
    # ---- v5: v4'ün gerçek e-postalarda yanlış alarm verdiği türler (hesap güvenliği, "Tebrikler") ----
    ("lv01", L, "diger", "eposta", "Subject: Confirm your email\nThanks for signing up for {app}! To activate your account and start using all features, confirm your email address using the button below. If you didn't create an account, you can safely ignore this email."),
    ("lv02", L, "diger", "eposta", "Konu: E-posta adresini doğrula\nMerhaba Ad Soyad, {shop} hesabını oluşturduğun için teşekkürler. Hesabını etkinleştirmek için aşağıdaki butona tıklayarak e-posta adresini doğrulaman yeterli. Bu kaydı sen yapmadıysan bu e-postayı dikkate alma."),
    ("lv03", L, "otp_kod", "eposta", "Subject: Verify it's you\nSomeone is trying to sign in to your {app} account from a device we don't recognize ({city}, Turkey). Enter this code on that device to continue: {code6}. If this wasn't you, change your password."),
    ("lv04", L, "diger", "eposta", "Konu: Şifre sıfırlama talebin\nMerhaba, {shop} hesabın için şifre sıfırlama talebi aldık. Yeni şifreni belirlemek için aşağıdaki bağlantıyı 1 saat içinde kullanabilirsin. Talep sana ait değilse şifren değişmeyecek, bu e-postayı silebilirsin."),
    ("lv05", L, "diger", "eposta", "Subject: Your password was changed\nThe password for your {app} account was changed on {date}. If you made this change, no further action is needed. If not, recover your account from the sign-in page right away."),
    ("lv06", L, "diger", "eposta", "Konu: Hesabında yeni bir oturum açıldı\n{app} hesabına {date} tarihinde yeni bir cihazdan ({city}, Türkiye) giriş yapıldı. Bu sendin değilse ayarlar > güvenlik bölümünden oturumu kapatıp şifreni değiştirebilirsin."),
    ("lv07", L, "diger", "eposta", "Subject: Security incident notice - action recommended\nWe recently identified unauthorized access to a limited part of our infrastructure. As a precaution, we recommend rotating any API keys stored in your {app} projects. We'll share a full report on our status page."),
    ("lv08", L, "fatura", "eposta", "Subject: Payment failed - service suspended\nWe couldn't charge your card for your {app} subscription ({amount}). Your services have been paused until the invoice is paid. You can update your payment method from the billing page in your dashboard."),
    ("lv09", L, "banka", "eposta", "Konu: Tebrikler, kredini kapattın! 🎉\nMerhaba Ad Soyad, {shop} alışveriş kredinin son taksiti olan {amount} ödendi ve kredin kapandı. Bizi tercih ettiğin için teşekkürler."),
    ("lv10", L, "diger", "eposta", "Konu: Tebrikler, üyeliğin aktif!\n{app} Premium üyeliğin başladı. İlk ödemen {date} tarihinde alınacak. Üyeliğini istediğin zaman hesap ayarlarından iptal edebilirsin."),
    ("lv11", L, "bahis", "eposta", "Konu: Tebrikler, kuponunuz kazandı\nMisli.com: {date} tarihinde oynadığınız {amount} tutarlı iddaa kuponunuz kazandı. Kazancınız hesap bakiyenize eklenmiştir. Kupon detayları için Kuponlarım sayfasını ziyaret edin."),
    ("lv12", L, "diger", "sms", "Tebrikler! {shop} kart basvurunuz onaylanmistir. Kartiniz 5 is gunu icinde kayitli adresinize gonderilecektir. {b}"),
    ("lv13", L, "diger", "eposta", "Konu: Uygulamaya erişim izni verdiniz\n{app} uygulamasının Google Hesabınızdaki bazı verilere erişmesine izin verdiniz. Bu izni siz vermediyseniz hesap ayarlarınızdaki Üçüncü taraf erişimi bölümünden kaldırabilirsiniz."),
    ("lv14", L, "diger", "eposta", "Subject: Welcome back - your account has been recovered\nYour {app} account was successfully recovered on {date}. If you didn't do this, someone else may have access; review your recent activity and security settings."),
    ("lr01", L, "ilan_alisveris", "eposta", "Konu: Araç kiralama rezervasyon onayı\nRezervasyon no: {ref}. Aracınızı {date} {time}'de {city} Havalimanı ofisimizden teslim alabilirsiniz. Ödeme teslim sırasında sürücü adına kayıtlı kredi kartıyla alınacaktır; depozito kartınızda provizyon olarak bloke edilir."),
    ("lr02", L, "ilan_alisveris", "eposta", "Konu: Otel rezervasyonunuz onaylandı\n{city}'deki konaklamanız için rezervasyonunuz onaylandı. Giriş: {date}. Toplam {amount} tutar kartınızdan tahsil edilmiştir. Rezervasyonunuzu uygulamadaki Seyahatlerim bölümünden yönetebilirsiniz."),
    ("lr03", L, "diger", "sms", "{ref} numarali hasar dosyaniz icin eksper atamasi yapilmistir. Dosyanizin durumunu sigorta sirketinizin uygulamasindan veya {phone} numarali cagri merkezinden takip edebilirsiniz. {b}"),
    ("lr04", L, "ilan_alisveris", "sms", "Arac kiralama sozlesmeniz olusturulmustur. Teslim: {date} {time}, {city}. Depozito {amount} kredi kartinizda bloke edilmistir, arac iadesinden sonra 7 gun icinde serbest birakilacaktir. {b}"),
    # ---------------- Dolandırıcılık: linksiz / sohbet / sosyal mühendislik ----------------
    ("fs01", F, "banka", "whatsapp", "Iyi gunler, {bank} guvenlik biriminden ariyorum, size ulasamadik. Hesabinizdan yurt disina {amount} cikis talebi var. Durdurmamiz icin size simdi gonderecegimiz onay kodunu bu numaraya yazar misiniz?"),
    ("fs02", F, "banka", "telegram", "Öğrencilere iş fırsatı! Banka kartını 1 haftalığına kiralamamıza izin ver, haftalık {amount} öde. Kartı şirketin ödemelerinde kullanacağız, hiçbir risk yok. DM."),
    ("fs03", F, "devlet", "whatsapp", "Sayın Ad Soyad, ben {city} Cumhuriyet Başsavcılığı'ndan. Adınıza açılmış bir hesabın suç gelirlerinde kullanıldığı tespit edildi. Soruşturmanın gizliliği gereği kimseyle paylaşmayın, bugün sizi arayacağım."),
    ("fs04", F, "devlet", "sms", "Sn. Ad Soyad, icra dosyaniz kesinlesmistir. Maas haczi baslamadan once {phone} numarali hukuk burosuyla gorusmeniz gerekmektedir."),
    ("fs05", F, "devlet", "sms", "Sn. Ad Soyad evraklariniz tahkim merkezimize ulasmistir, magdur olmamak icin acilen arayiniz. {phone}"),
    ("fs06", F, "tanidik", "whatsapp", "{rel} benim, eski hattım kapandı bu numaradan yazıyorum. Bankadan para çekemiyorum, kira bugün ödenmezse sorun çıkacak, {amount} gönderebilir misin? Hesap: {iban}"),
    ("fs07", F, "tanidik", "whatsapp", "{rel} n'olur hemen dön, {name} kaza geçirdi, ameliyat parası yatırmamız gerekiyor. Benim kartım limit doldu, {amount} gönderebilir misin şu hesaba, yarın ilk iş iade ederim. {iban}"),
    ("fs08", F, "otp_kod", "whatsapp", "Kanka pardon yanlışlıkla senin numaranı yazmışım, sana 6 haneli bir kod gitti, onu bana atar mısın? 😅"),
    ("fs09", F, "ilan_alisveris", "sms", "Merhaba, ilanınızdaki ürünü almak istiyorum. Kargo kodu telefonunuza SMS ile gelecek, kodu bana iletirseniz kargoyu hemen oluşturuyorum 🙏"),
    ("fs10", F, "ilan_alisveris", "whatsapp", "Selamlar, arsa/daire satıyorum, sahibinden fiyatının yarısına. Tapu işlemleri için avukatım ilgileniyor, sıra almak için {amount} ön ödeme gerekiyor. Fotoğrafları WhatsApp'tan atayım mı?"),
    ("fs11", F, "ilan_alisveris", "sms", "Merhaba, ilaninizdaki urun icin odemeyi guvenli odeme ile yaptim. Paranizin hesabiniza aktarilmasi icin size gelen onay kodunu iletmeniz gerekiyor."),
    ("fs12", F, "is_ilani", "whatsapp", "Merhaba, profilinizi gördük. Evden yarı zamanlı ürün değerlendirme işi, günlük {amount} kazanç. Detaylar için WhatsApp'tan dönüş yapabilir misiniz?"),
    ("fs13", F, "is_ilani", "telegram", "Kolay ek gelir: Uygulamaya yorum yazdığın her ürün için komisyon kazanıyorsun. Hesabına {amount} birikti ama çekebilmek için seviye atlaman ve {small} aktivasyon ücreti yatırman lazım."),
    ("fs14", F, "is_ilani", "sms", "Kurye alimi! Motor sarti yok, ekipman depozitosu {amount}, ilk hafta iade edilir. Basvuru icin {phone}"),
    ("fs15", F, "yatirim", "whatsapp", "Günaydın değerli üyeler ☀️ Dünkü sinyalimiz {pct} kazandırdı. Hocamızın VIP grubuna geçmek isteyenler asistanıma özelden yazsın, kontenjan sınırlı."),
    ("fs16", F, "yatirim", "whatsapp", "Selam! Geçen hafta {city}'deki konferansta tanışmıştık sanırım, numaranı {name}'den aldım 😊 Hatırladın mı beni?"),
    ("fs17", F, "yatirim", "telegram", "Hey! I'm the assistant of a crypto analyst. Our members made {pct} this week with the AI trading bot. Minimum start is 300 USDT. Want the registration link?"),
    ("fs18", F, "tanidik", "sms", "Ev sahibinizin bankasi degisti, bu aydan itibaren kira odemelerini {iban} numarali hesaba yapmaniz rica olunur. Emlak ofisi"),
    ("fs19", F, "diger", "sosyal_medya", "🙏 Depremzede ailemiz çadırda kalıyor, kış gelmeden konteyner alabilmemiz için desteğinizi bekliyoruz. Her 100 TL bir ısıtıcı demek. IBAN: {iban}"),
    ("fs20", F, "operator_abonelik", "eposta", "Konu: Sipariş onayı #{ref}\n{brand} üzerinden {amount} tutarında dizüstü bilgisayar siparişiniz alındı. Bu siparişi siz vermediyseniz iade süreci için müşteri hizmetlerimize hemen ulaşın: {phone}"),
    ("fs21", F, "oyun", "sosyal_medya", "Merhaba, e-spor ajansıyız. Yayınların dikkatimizi çekti, sponsorluk görüşmesi için önce hesabının doğrulanması gerekiyor. Doğrulama sayfası: {app_fake}"),
    ("fs22", F, "oyun", "whatsapp", "Abi {game} hesabını satıyormuşsun, alıcıyım. Ödemeyi aracı siteden yaptım, onaylaman için hesap şifreni ve mailine gelen kodu atman lazım."),
    ("fs23", F, "is_ilani", "eposta", "Subject: Remote position - immediate start\nYour resume was shortlisted for a remote role paying $45/hour. Before onboarding you need to purchase the work laptop from our vendor; the cost will be reimbursed with your first paycheck."),
    ("fs24", F, "banka", "sms", "Sayin musterimiz, kredi karti aidat iadeniz onaylanmistir. Iadenin yapilmasi icin musteri temsilcimiz sizi arayacak, telefonunuza gelecek kodu temsilciye iletiniz."),
    ("fs25", F, "odul_cekilis", "whatsapp", "Tebrikler! {shop} çekilişinde ödül kazanan 10 kişiden birisiniz 🎉 Kargo ücreti {small} ödendikten sonra ödülünüz gönderilecek. Ödeme için IBAN: {iban}"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--per-template", type=int, default=30)
    ap.add_argument("--val-frac", type=float, default=0.12)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    ids = [t[0] for t in TEMPLATES]
    assert len(ids) == len(set(ids)), "şablon id'leri benzersiz olmalı"
    # Doğrulama şablonları her etiketten ayrı seçilir; yoksa bir sınıf hiç ölçülemeyebilir
    val_templates = set()
    for lab in (L, S, F):
        pool = [t[0] for t in TEMPLATES if t[1] == lab]
        val_templates |= set(rng.sample(pool, max(1, int(len(pool) * args.val_frac))))

    out, seen = [], set()
    for tid, label, category, channel, template in TEMPLATES:
        # Spam şablonu az; sınıf dengesi için her spam şablonundan daha çok örnek üretilir
        target = int(args.per_template * (2.5 if label == S else 1))
        for _ in range(target * 3):  # tekrarlar atlanınca hedefe ulaşmak için yedek deneme
            if sum(1 for r in out if r["template"] == tid) >= target:
                break
            text = fill(template, rng)
            # İki sınıfa aynı oranda: kişisel ayrıntı ne gerçeklik ne dolandırıcılık işareti olmalı
            if label in (F, L) and rng.random() < 0.3:
                text = personalize(text, rng)
            # Gerçek kurum mesajlarında tarih/saat çok sık; dolandırıcılıkta da geçsin ki tek başına güven işareti olmasın
            if label == F and rng.random() < 0.35 and not re.search(r"\d{2}\.\d{2}\.20\d{2}", text):
                text = text.rstrip() + rng.choice([" Son tarih: {d} {t}.", " ({d} {t})", " Islem: {d} {t}."]).format(
                    d=f"{rng.randint(1, 28):02d}.{rng.randint(1, 12):02d}.2026", t=f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}")
            text = style(text, channel, rng)
            if text in seen:
                continue
            seen.add(text)
            out.append({"id": make_id(text, prefix="t"), "text": text, "label": label, "category": category,
                        "channel": channel, "source": "sentetik", "is_synthetic": True, "template": tid,
                        "split": "val" if tid in val_templates else "train"})
    rng.shuffle(out)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")

    from collections import Counter
    print(f"{len(TEMPLATES)} şablon, {len(out)} mesaj → {args.out}")
    print("Etiket:", dict(Counter(r["label"] for r in out)))
    print("Bölüm:", dict(Counter(r["split"] for r in out)))


if __name__ == "__main__":
    main()
