# Fine-tuning planı

## Hedef
Rakip modelin (Horizon-Labs/phishing-scam-detector-base) gerçek Türk kurum mesajlarındaki yanlış alarmını
(%51) düşürmek; dolandırıcılık yakalamayı ve diğer dillerdeki başarısını korumak.

## Neden rakip bu kadar yanlış alarm veriyor
Model kartına göre eğitim verisi: 98 bin sentetik mesaj (Qwen ile üretilmiş) + temiz örnek olarak 59 bin
web metni (FineWeb). Temiz tarafta gerçek banka/kargo/e-Devlet bildirimi yok denecek kadar az. Model
"kargo + link + tutar" görünce dolandırıcılık diyor, çünkü bu kalıbın temiz halini hiç görmemiş.

## Başlangıç modeli
- **Ana yol:** rakibin kendisi (mmBERT-base, 307M parametre, Apache-2.0). Üstüne eğitim türev çalışma
  sayılır; model kartında rakibe atıf ve lisans korunur.
- **Karşılaştırma:** jhu-clsp/mmBERT-small (140M, MIT), sıfırdan aynı veriyle. Daha küçük, telefonda koşar.

## Donanım (RTX 4050, 6 GB)
- 307M parametrenin 197M'i kelime gömmesi (256k kelimelik sözlük). Gömmeler dondurulur, kalan ~110M
  eğitilir → AdamW durumu ~1.8 GB, bf16 ile aktivasyonlar sığar.
- Maks. uzunluk 256 token (SMS'ler için fazlasıyla yeter; e-posta kırpılır).
- Torch şu an CPU sürümü; CUDA sürümü kurulacak (~2.5 GB, download.pytorch.org).
- Yetmezse: kiralık GPU (RunPod/Vast, saati ~0.3-0.5 $; tüm eğitim 1 saatin altında).

## Eğitim verisi (test setlerinden TAMAMEN ayrı)
Test setleri: `data/real_tr.jsonl`, `data/real_email.jsonl`, `data/seed_hard_tr.jsonl`,
`data/seed_hard2_tr.jsonl`. Bunların hiçbiri ve şablon kopyaları eğitime girmez.

1. **Sentetik TR eğitim seti (ana kaynak):** ~300 elle yazılmış şablon × otomatik varyasyon
   (kurum adı, tutar, tarih, kod, alan adı). Hedef ~5.000 mesaj:
   - temiz kurum bildirimi (banka, kargo, operatör, e-Devlet, OTP, fatura): %40
   - reklam (spam): %25
   - dolandırıcılık: %35; özellikle linksiz/sohbet tarzı, sahte destek hattı, OTP isteme
   - sahte ↔ gerçek karşıt çiftler (aynı konu, farklı alan adı/talep)
2. **Unutmayı önlemek için:** UCI SMS Spam Collection (İngilizce, CC BY 4.0) ve UCI Turkish Spam V01
   (e-posta, CC BY 4.0) küçük oranda. Lisansı belirsiz setler (Kaggle Turkish SMS Collection) kullanılmaz.
3. **Sızıntı kontrolü:** her eğitim mesajı tüm test mesajlarıyla kelime kümesi benzerliğine bakılır;
   0.5 üstü benzerlik varsa atılır (`check_leakage.py`).

## Ölçüm (her deneyde rakiple yan yana)
- Gerçek SMS: temiz mesajlarda yanlış alarm oranı, spam doğruluğu
- Zor setler: dolandırıcılık yakalama, karşıt çift doğruluğu (ikisi birden doğru)
- İngilizce ayrılmış set: rakibe göre gerileme var mı
- Hedef: gerçek SMS yanlış alarm %51 → %10 altı; zor set fraud yakalama ≥ %88 (rakip seviyesi)

## Adımlar
1. CUDA torch kurulumu, GPU testi
2. `gen_train.py` (şablon + varyasyon) ve `check_leakage.py`
3. `train.py`: gömmeler dondurulmuş, bf16, lr 2e-5, 3 epoch, en iyi checkpoint ayrılmış doğrulama setinden
4. `test_rival.py --model checkpoints/...` ile tüm test setlerinde karşılaştırma
5. İyiyse Hugging Face: model + benchmark veri seti (CC BY 4.0) + model kartı
6. Sonraki proje: açıklama üreten küçük model ("neden şüpheli")
