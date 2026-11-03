"""Bulwark modelini tarayıcıda (transformers.js) çalışması için ONNX'e çevirir.

Kullanım:
    python export_onnx.py release/bulwark-scam-detector
Çıktı: <klasör>/onnx/model.onnx (fp32) ve onnx/model_fp16.onnx (yarım hassasiyet, Space bunu kullanır)

int8 dinamik sıkıştırma denendi ve gerçek SMS + zor setlerde kararların ~%4'ünü değiştirdi (temizde yanlış alarm
arttı). fp16 536 mesajın hiçbirinde kararı değiştirmedi, en büyük olasılık farkı 0.008.
"""
import sys
from pathlib import Path

import onnx
import torch
from onnxruntime.transformers.float16 import convert_float_to_float16
from transformers import AutoModelForSequenceClassification, AutoTokenizer

src = Path(sys.argv[1])
out = src / "onnx"
out.mkdir(exist_ok=True)

tok = AutoTokenizer.from_pretrained(src)
model = AutoModelForSequenceClassification.from_pretrained(src, attn_implementation="eager").eval()
enc = tok(["Kargonuz teslim edilemedi, adres icin tiklayin", "Merhaba"], return_tensors="pt", padding=True)

batch, seq = torch.export.Dim("batch"), torch.export.Dim("sequence")
torch.onnx.export(
    model,
    (),
    out / "model.onnx",
    kwargs={"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"]},
    input_names=["input_ids", "attention_mask"],
    output_names=["logits"],
    dynamic_shapes={"input_ids": {0: batch, 1: seq}, "attention_mask": {0: batch, 1: seq}},
    dynamo=True,
    external_data=False,
)
m = onnx.load(out / "model.onnx")
m.graph.ClearField("value_info")  # dışa aktarıcının ara şekil bilgisi hatalı, dönüştürücüyle çakışıyor
onnx.save(convert_float_to_float16(m, keep_io_types=True), out / "model_fp16.onnx")
for f in sorted(out.glob("*.onnx")):
    print(f.name, f"{f.stat().st_size / 1e6:.0f} MB")
