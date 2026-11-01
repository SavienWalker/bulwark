"""Mesaj kutusu dışından gelen gerçek örnekleri (ekran görüntüsünden metne çevrilmiş sahte sayfa, DM vb.)
data/real_misc.jsonl dosyasına ekler. Metin maskelenir, aynı metin iki kez eklenmez.

Kullanım:
    python add_real_misc.py
Yeni örnek eklemek için aşağıdaki RECORDS listesine bir kayıt ekleyip betiği yeniden çalıştırın.
"""
import json
import sys
from pathlib import Path

from mask_pii import make_id, mask_text

OUT = Path(__file__).parent / "data/real_misc.jsonl"

RECORDS = [
    {
        "text": (
            "Google Müşteri Ödül Programı\n"
            "Tebrikler! 13 Temmuz 2026\n"
            "Her gün, müşteri memnuniyet anketimize katılması için küçük bir Google kullanıcı grubunu seçiyoruz ve onlara "
            "ortaklarımızdan ve sponsorlarımızdan özel hediyeler alma şansı veriyoruz. Bu, Google'ı seçtiğiniz için size "
            "teşekkür etme yöntemimizdir.\n"
            "Katılarak ücretsiz bir iPhone 17 Pro, Samsung Galaxy S25, 1000 $ Walmart Hediye Kartı, 1000 $ Paypal Hediye "
            "Kartı veya 3 yıllık ücretsiz Netflix üyeliği kazanma şansına sahip olursunuz. Bu anket müşterilerimizi daha "
            "iyi anlamamızı sağlar ve zamanınızın 30 saniyesinden daha azını alır.\n"
            "Unutmayın: Rastgele seçilen 100 müşteri bu daveti aldı ve hediye sayısı sınırlıdır.\n"
            "Müşterilerimiz arasından bu şansı bir sonraki şanslı kişiye vermeden önce aşağıdaki soruları yanıtlamak için "
            "1 dakika 30 saniye süreniz var!\n"
            "Şu anda ne tür bir cihaz kullanıyorsunuz? PC / Dizüstü Bilgisayar · Akıllı Telefon · Tablet"
        ),
        "label": "fraud",
        "category": "odul_cekilis",
        "difficulty": "orta",
        "channel": "diger",
        "hard_tags": ["resmi_dil", "aciliyet", "cok_adimli"],
        "explanation": (
            "Google adına sahte ödül anketi; ABD'ye özgü hediyeler (Walmart), 'seçilmiş 100 kişi' ve geri sayımla acele "
            "ettiriyor. Anketin sonunda genelde kargo ücreti adıyla kart bilgisi istenir."
        ),
        "date": "2026-07",
        "notes": "Kullanıcının telefonunda tarayıcıda açılan yönlendirme sayfası; ekran görüntüsünden metne çevrildi.",
    },
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    existing = []
    if OUT.exists():
        existing = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen = {r["id"] for r in existing}
    added = 0
    for rec in RECORDS:
        text, _ = mask_text(rec["text"])
        rid = make_id(text, prefix="m")
        if rid in seen:
            continue
        existing.append({"id": rid, **rec, "text": text, "source": "kendi_gelen_kutusu", "is_synthetic": False,
                         "sender_type": "bilinmiyor", "labeled_by": "insan"})
        seen.add(rid)
        added += 1
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in existing), encoding="utf-8")
    print(f"{added} yeni kayıt eklendi, toplam {len(existing)} → {OUT}")


if __name__ == "__main__":
    main()
