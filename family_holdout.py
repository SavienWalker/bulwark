"""Şablon ailesi dışarıda bırakma testi (forumda nootxlm'in önerisi).

Kullanım:
    python family_holdout.py build   # eğitim dosyası + ölçüm dilimi üretir
    python family_holdout.py eval checkpoints/v5 checkpoints/v5-famho

Seçilen ailelerin bütün şablonları (yakın varyantlar dahil) eğitimden ve doğrulamadan tamamen çıkarılır.
Model bu dolandırıcılık ifadelerini hiç görmeden eğitilir; yakalama oranı sadece o ailelerde ölçülür:
  1) o şablonlardan üretilmiş sentetik mesajlar
  2) zor setlerde aynı ailelere ait elle yazılmış mesajlar
"""
import json
import sys
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from test_rival import MODEL_ID, predict

sys.stdout.reconfigure(encoding="utf-8")

FAMILIES = {
    "kargo/gümrük ücreti": {
        "templates": ["fk01", "fk02", "fk03", "fk04", "fw25"],
        "hard": ["h-f05", "h-f16", "h2-f13", "h2-f36"],
    },
    "tanıdık taklidi": {
        "templates": ["fs06", "fs07", "fs08"],
        "hard": ["h-f07", "h-f20", "h2-f20", "h2-f30"],
    },
    "iş/görev ve hesap kiralama": {
        "templates": ["fs02", "fs12", "fs13", "fs14", "fs23", "fw08", "fw09", "fw19", "fw20", "fw21", "fw22",
                      "fw23", "fw24"],
        "hard": ["h-f03", "h-f17", "h2-f12", "h2-f26", "h2-f37"],
    },
    "hukuki tehdit": {
        "templates": ["fs03", "fs04", "fs05", "fw15", "fw16", "fp05"],
        "hard": ["h2-f04", "h2-f05"],
    },
}
HELD = {t for f in FAMILIES.values() for t in f["templates"]}
TRAIN_IN, TRAIN_OUT = Path("data/train_mix_v5.jsonl"), Path("data/train_mix_famho.jsonl")
SLICE = Path("data/external/heldout_families.jsonl")
THRESHOLD = {"bulwark": 0.6, "rival": 0.5}


def read(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def build():
    mix = read(TRAIN_IN)
    keep = [r for r in mix if r.get("template") not in HELD]
    TRAIN_OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep), encoding="utf-8")
    family_of = {t: name for name, f in FAMILIES.items() for t in f["templates"]}
    held = [{**r, "family": family_of[r["template"]]} for r in read("data/train_synth.jsonl") if r["template"] in HELD]
    SLICE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in held), encoding="utf-8")
    missing = HELD - {r["template"] for r in held}
    print(f"eğitim: {len(mix)} → {len(keep)} ({len(mix) - len(keep)} kayıt çıkarıldı); dilim: {len(held)} mesaj")
    if missing:
        print("  uyarı: sızıntı kontrolünde tamamen atılmış şablonlar:", sorted(missing))


def evaluate(models):
    held = read(SLICE)
    hard_ids = {i: name for name, f in FAMILIES.items() for i in f["hard"]}
    hard = [{**r, "family": hard_ids[r["id"]]} for p in ("data/seed_hard_tr.jsonl", "data/seed_hard2_tr.jsonl")
            for r in read(p) if r["id"] in hard_ids]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    cols = ["rakip"] + [Path(m).name for m in models]
    table = {}
    for mid, col in zip([MODEL_ID] + models, cols):
        tok = AutoTokenizer.from_pretrained(mid)
        model = AutoModelForSequenceClassification.from_pretrained(mid).to(device).eval()
        id2 = {int(k): v.lower() for k, v in model.config.id2label.items()}
        t = THRESHOLD["rival" if mid == MODEL_ID else "bulwark"]
        for name, rows in (("sentetik", held), ("zor set", hard)):
            probs = predict(model, tok, [r["text"] for r in rows], 16)
            for r, p in zip(rows, probs):
                d = {id2[i]: v for i, v in enumerate(p)}
                key = (name, r["family"], col)
                k, n = table.get(key, (0, 0))
                table[key] = (k + (d["fraud"] + d["spam"] > t), n + 1)
        del model
        torch.cuda.empty_cache()

    print("İstenmeyen olarak yakalanan dolandırıcılık (rakip eşik 0.5, Bulwark eşik 0.6)\n")
    print("| Dilim | Aile | " + " | ".join(cols) + " |\n|---|---|" + "---|" * len(cols))
    for name in ("sentetik", "zor set"):
        for fam in list(FAMILIES) + ["TOPLAM"]:
            cells = []
            for col in cols:
                if fam == "TOPLAM":
                    k = sum(v[0] for kk, v in table.items() if kk[0] == name and kk[2] == col)
                    n = sum(v[1] for kk, v in table.items() if kk[0] == name and kk[2] == col)
                else:
                    k, n = table.get((name, fam, col), (0, 0))
                cells.append(f"{k}/{n} ({k / n:.0%})" if n else "-")
            print(f"| {name} | {fam} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    else:
        evaluate(sys.argv[2:])
