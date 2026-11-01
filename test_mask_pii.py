"""mask_pii için hızlı testler. Çalıştır: python test_mask_pii.py"""
import sys

from mask_pii import mask_text

sys.stdout.reconfigure(encoding="utf-8")

CASES = [
    # (girdi, beklenen çıktı)
    ("Beni 0532 123 45 67'den ara", "Beni 0500 000 00 00'den ara"),
    ("Tel: +90 532 123 4567", "Tel: 0500 000 00 00"),
    ("05321234567 numarasına yaz", "0500 000 00 00 numarasına yaz"),
    ("IBAN: TR33 0006 1005 1978 6457 8413 26", "IBAN: TR00 0000 0000 0000 0000 0000 00"),
    ("Kart 4111 1111 1111 1111 ile", "Kart 0000 0000 0000 0000 ile"),
    ("TC: 10000000146", "TC: 00000000000"),
    ("Mail: ali.veli@gmail.com", "Mail: ornek@example.com"),
    ("Takip no 4500123456 ile", "Takip no 0000000000 ile"),
    ("Linke tıkla ptt-kargo.com/t/Ab12Cd34Ef", "Linke tıkla ptt-kargo.com/t/xxxx"),
    ("Sayın AHMET YILMAZ, kartınız", "Sayın Ad Soyad, kartınız"),
    ("Sayın Ayşe Demir faturanız hazır", "Sayın Ad Soyad faturanız hazır"),
    ("Sayin MEHMET DEMIR,1234 ile biten", "Sayin Ad Soyad,1234 ile biten"),
    ("14:19'da Ali Veli alicisina 1234-12345678-123 numarali", "14:19'da Ad Soyad alicisina 0000-00000000-000 numarali"),
    ("paylasmayiniz. AYSE KAYA YILMAZ alicisina, 800 TL", "paylasmayiniz. Ad Soyad alicisina, 800 TL"),
    ("123 - 4567890 hesaptan Ali Veli adina 14.000,00 TL", "000 - 0000000 hesaptan Ad Soyad adina 14.000,00 TL"),
    ("06 ABC12 plakali VOLVO", "00 XXX00 plakali VOLVO"),
    ("IP Adresi 81.214.10.20 Konum", "IP Adresi 0.0.0.0 Konum"),
    ("Tutar 1.249,90 TL", "Tutar 1.249,90 TL"),
    ("nolu gonderiniz Leyla Kaya  (Gorevli) teslim edilmistir", "nolu gonderiniz Ad Soyad  (Gorevli) teslim edilmistir"),
    ("34 ABC 123 plakali araç", "00 XXX 000 plakali araç"),
    ("10 GB 500 dakika", "10 GB 500 dakika"),
    ("kesinti yasamamaniz adina bugune", "kesinti yasamamaniz adina bugune"),
    # Değişmemesi gerekenler
    ("Sayın Müşterimiz, kartınız hazır", "Sayın Müşterimiz, kartınız hazır"),
    ("Doğrulama kodunuz: 482913", "Doğrulama kodunuz: 482913"),
    ("Tutar 1.249,90 TL, tarih 05.11.2026", "Tutar 1.249,90 TL, tarih 05.11.2026"),
    ("Bilgi için 0850 000 00 00 arayın", "Bilgi için 0850 000 00 00 arayın"),
    ("Bilgi için 444 0 000", "Bilgi için 444 0 000"),
    ("Detay: mediamarkt.com.tr/kampanya", "Detay: mediamarkt.com.tr/kampanya"),
    # Geçersiz TCKN de 9+ haneli sayı kuralıyla sıfırlanır
    ("Geçersiz TC 12345678901", "Geçersiz TC 00000000000"),
]

failed = 0
for given, expected in CASES:
    got, _ = mask_text(given)
    if got != expected:
        failed += 1
        print(f"✗ {given!r}\n    beklenen: {expected!r}\n    gelen:    {got!r}")
print(f"{len(CASES) - failed}/{len(CASES)} test geçti")
sys.exit(1 if failed else 0)
