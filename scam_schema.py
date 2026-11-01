"""Veri seti şeması: izin verilen değerler ve zorunlu alanlar. Diğer scriptler buradan okur."""

LABELS = ("fraud", "spam", "legitimate")

CATEGORIES = (
    "kargo",              # kargo, gümrük, teslimat
    "banka",              # hesap, kart, kredi, transfer
    "devlet",             # e-Devlet, vergi, emniyet, mahkeme, MTV
    "fatura",             # elektrik, su, doğalgaz, HGS/OGS
    "operator_abonelik",  # GSM operatörü, Netflix, dijital abonelik
    "otp_kod",            # doğrulama kodu gönderme / isteme
    "tanidik",            # aile, arkadaş, tanıdık taklidi veya gerçek sohbetteki para isteği
    "yatirim",            # kripto, borsa, halka arz, forex
    "is_ilani",           # iş teklifi, evden çalışma, kuryelik
    "odul_cekilis",       # çekiliş, hediye, anket ödülü
    "ilan_alisveris",     # ikinci el ilan, kapora, alışveriş siparişi/iade
    "oyun",               # Steam, Discord, e-pin, oyun içi
    "sosyal_medya",       # Instagram, telif, hesap kapatma
    "saglik",             # MHRS, e-Nabız, aile hekimi
    "kampanya",           # mağaza/marka reklamı, indirim
    "bahis",              # bahis/kumar
    "sohbet",             # kişisel sohbet
    "diger",
)

DIFFICULTIES = ("kolay", "orta", "zor")

CHANNELS = ("sms", "imessage", "whatsapp", "telegram", "eposta", "sosyal_medya", "diger")

SOURCES = (
    "kendi_gelen_kutusu",  # etiketleyicinin kendi telefonu
    "bagis",               # başkasının bağışladığı mesaj
    "kamu_uyarisi",        # banka/kurum/USOM uyarı sayfasındaki örnek
    "elle_yazildi",        # gerçek örneklerden esinlenerek elle yazıldı
    "sentetik",            # model tarafından üretildi
)

# Zorluğu açıklayan etiketler (birden fazla seçilebilir)
HARD_TAGS = (
    "link_yok",
    "benzer_alan_adi",       # yurticikargo.com-teslimat.info gibi
    "gercek_alan_adi",       # mesajdaki alan adı kurumun gerçek alan adı
    "kisaltilmis_link",
    "resmi_dil",
    "sohbet_tonu",
    "gercek_kurum_bildirimi",
    "uyari_iceriyor",        # "kimseyle paylaşmayın", "bilginiz dışındaysa" vb.
    "aciliyet",
    "para_tutari",
    "kod_iceriyor",
    "cok_adimli",            # önce cevap/güven ister, asıl istek sonra gelir
)

REQUIRED_FIELDS = ("id", "text", "label", "category", "difficulty", "channel", "source", "is_synthetic")

# Bu alanlar isteğe bağlı
OPTIONAL_FIELDS = (
    "hard_tags",    # list[str], HARD_TAGS içinden
    "explanation",  # str, neden bu etiket (fraud/spam için önerilir)
    "pair",         # str, aynı konudaki karşıt örnekle ortak kimlik (ör. "mtv")
    "ambiguous",    # bool, true ise ana metriklere girmez
    "labeled_by",   # "insan" | "claude_onayli" (Claude önerdi, insan Enter ile onayladı)
    "sender_type",  # "alfanumerik" | "kisa_kod" | "numara" | "bilinmiyor"
    "date",         # "YYYY-MM"
    "notes",
)
