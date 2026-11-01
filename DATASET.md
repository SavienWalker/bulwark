# Türkçe Zor Dolandırıcılık Test Seti

Amaç: mevcut modellerin zorlandığı Türkçe mesajları ölçmek.
- **Kurnaz dolandırıcılık:** linksiz, sohbet tonunda, gerçeğe çok benzeyen alan adlı.
- **Zor temiz:** gerçek kurum bildirimleri. Kargo, banka, e-Devlet, HGS, operatör, doğrulama kodu.

Bu set **test** içindir. Eğitim verisiyle karışmamalı; aynı mesaj ikisinde birden olmamalı.

## Kayıt formatı (JSONL, satır başına bir mesaj)

```json
{"id": "h-f10", "text": "...", "label": "fraud", "category": "devlet", "difficulty": "zor",
 "channel": "sms", "source": "elle_yazildi", "is_synthetic": true,
 "hard_tags": ["benzer_alan_adi", "resmi_dil"], "pair": "mtv",
 "explanation": "gib.gov.tr yerine gib-hizliodeme.com; e-Devlet şifresi isteniyor."}
```

| Alan | Zorunlu | Değerler |
|---|---|---|
| `id` | evet | Tekil. `h-` elle yazılan, `r-` gerçek mesaj |
| `text` | evet | **Maskelenmiş** mesaj metni |
| `label` | evet | `fraud` · `spam` · `legitimate` |
| `category` | evet | `scam_schema.py` → `CATEGORIES` |
| `difficulty` | evet | `kolay` · `orta` · `zor` |
| `channel` | evet | `sms` · `imessage` · `whatsapp` · `telegram` · `eposta` · `sosyal_medya` · `diger` |
| `source` | evet | `kendi_gelen_kutusu` · `bagis` · `kamu_uyarisi` · `elle_yazildi` · `sentetik` |
| `is_synthetic` | evet | Gerçek mesaj değilse `true` |
| `hard_tags` | hayır | `scam_schema.py` → `HARD_TAGS` |
| `explanation` | hayır | Neden bu etiket? fraud/spam için yazılması önerilir |
| `pair` | hayır | Karşıt örnekle ortak anahtar (sahte MTV ↔ gerçek MTV) |
| `ambiguous` | hayır | `true` ise ana metriklere girmez |
| `labeled_by` | hayır | `insan` (elle etiketlendi) · `claude_onayli` (Claude önerdi, insan tek tek onayladı) |
| `sender_type` | hayır | `alfanumerik` · `kisa_kod` · `numara` · `bilinmiyor` |

## Etiket kuralları

Rakip modelle (Horizon-Labs) kıyaslanabilmek için aynı üç sınıf kullanılır:

- **fraud:** para, kart, şifre, kod, kimlik bilgisi veya güven çalmaya çalışır. Sahte link, sahte kurum, tanıdık taklidi, sahte iş/yatırım. *Asıl hamle sonraki mesajda gelecek olsa bile* (ör. "yanlış numara 😊" açılışı) fraud sayılır; emin değilsen `ambiguous: true` ekle.
- **spam:** gerçek bir işletmenin istenmeyen reklamı. Bir şey çalmaya çalışmaz. Genelde "RET yazıp gönderin" içerir.
- **legitimate:** diğer her şey: kurum bildirimleri, doğrulama kodları, kişisel sohbet. İçinde para, link veya uyarı geçse bile.

Sınır durumları:
- Yasa dışı bahis reklamı → `fraud` + `category: bahis` + `ambiguous: true`.
- Gerçek bankanın kredi reklamı → `spam`.
- Arkadaşın "hesabı böldüm, 420 TL at" mesajı → `legitimate` (`category: tanidik`).
- Bir karardan emin değilsen: etiketi yine de koy ve `ambiguous: true` ekle.

## Zorluk

- **kolay:** bariz sahte alan adı, abartılı vaat, yazım hatası.
- **orta:** inandırıcı ama tek bakışta yakalanabilir.
- **zor:** bir insan da duraksar. Linksiz, resmi dilli, gerçek kurum biçiminde ya da sohbet gibi.

Mümkün olduğunca **karşıt çift** ekle: aynı konuda bir sahte ve bir gerçek mesaj (`pair` alanı). Model sadece konuya bakıyorsa bu çiftlerde yakalanır.

## Kaynak önceliği

1. **Kendi gelen kutun** (`kendi_gelen_kutusu`): en değerli kaynak. Gerçek kurum bildirimleri ve sana gelmiş gerçek dolandırıcılıklar.
2. **Bağış** (`bagis`): sadece mesajın sahibinin açık izniyle. Maskelemeden önce kimseyle paylaşma.
3. **Kamu uyarıları** (`kamu_uyarisi`): bankaların, kurumların ve USOM'un yayınladığı örnek mesajlar. `notes` alanına kaynak URL'sini yaz.
4. **Elle yazılmış / sentetik:** sadece boşluk doldurmak için. Raporlarda gerçek ve sentetik sonuçlar **ayrı** gösterilir.

Kişilerin (rehberindekilerin) özel mesajları varsayılan olarak alınmaz. Yalnızca kurumlardan ve bilinmeyen numaralardan gelen mesajlar alınır.

## Maskeleme (`mask_pii.py`)

Yayından önce her mesaj maskelenir. Biçim korunur, değer sıfırlanır:

| Ne | Örnek → maske |
|---|---|
| Telefon | `0532 123 45 67` → `0500 000 00 00` |
| IBAN | `TR12 0006 ...` → `TR00 0000 0000 0000 0000 0000 00` |
| Kart no (Luhn geçerli) | → `0000 0000 0000 0000` |
| T.C. kimlik no (geçerli) | → `00000000000` |
| E-posta | → `ornek@example.com` |
| 9+ haneli sayı (takip no, müşteri no) | rakamlar `0` olur, uzunluk korunur |
| URL yolundaki kimlik parçaları | `site.com/t/Ab12Cd34Ef` → `site.com/t/xxxx` |
| "Sayın Ad Soyad" | → `Sayın Ad Soyad` |

**Alan adları korunur**: dolandırıcılığın en güçlü işareti onlar. 4–8 haneli doğrulama kodları korunur, çünkü süresi geçmiş kodlar kişisel veri sayılmaz.

Regex her şeyi yakalayamaz. Özellikle düz yazıdaki isimler ve adresler için etiketlerken **mesajı gözle kontrol et**. `validate_dataset.py` maskelenmemiş telefon, IBAN, kart, TCKN ve e-posta kalıntılarını raporlar.

## İş akışı

```bash
# 1a) iPhone: iTunes'ta şifresiz yedek al, sonra (en yeni yedeği kendisi bulur):
python import_iphone_backup.py data/candidates.jsonl

# 1b) Android: "SMS Backup & Restore" ile XML yedeği al, sonra:
python import_sms_backup.py sms-yedek.xml data/candidates.jsonl

# 1c) Elle: mesajları mesajlar.txt'ye yapıştır (aralarına '---' satırı), sonra:
python mask_pii.py mesajlar.txt data/candidates.jsonl

# 2) Etiketle (kaldığın yerden devam eder)
python label.py data/candidates.jsonl data/real_tr.jsonl

# 3) Doğrula
python validate_dataset.py data/real_tr.jsonl data/seed_hard_tr.jsonl

# 4) Rakibi ölç
python test_rival.py data/seed_hard_tr.jsonl --out results_seed.csv
```

iPhone yedeğinden alırken grup sohbetleri ve **cevap verdiğin kişilerin** mesajları varsayılan olarak alınmaz. Şifresiz yedek diskte telefonun neredeyse tüm verisini açık tutar: içe aktarma bitince yedeği sil ya da şifrelemeyi tekrar açıp yeni yedek al.

## Lisans

Planlanan: veri seti **CC BY 4.0**, kod **Apache-2.0**. Kamu uyarılarından alınan örneklerin kaynağı `notes` alanında belirtilir.
