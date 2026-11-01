# Bulwark

Turkish-first scam / spam / legitimate message detection: tooling, benchmark and model.

| | |
|---|---|
| 🤗 Model | [SavienWalker/bulwark-scam-detector](https://huggingface.co/SavienWalker/bulwark-scam-detector) |
| 🤗 Benchmark | [SavienWalker/bulwark-bench-tr](https://huggingface.co/datasets/SavienWalker/bulwark-bench-tr) |

On real Turkish SMS from a personal inbox, the existing multilingual detector
([Horizon-Labs/phishing-scam-detector-base](https://huggingface.co/Horizon-Labs/phishing-scam-detector-base))
raises a false alarm on **53%** of legitimate bank, cargo and e-Devlet messages. Bulwark, fine-tuned from it,
brings that to **14%** while still catching **98%** of unwanted messages. Full results:
[results_final_test.md](results_final_test.md) and the model card.

> 🇹🇷 Türkçe öncelikli dolandırıcılık/spam/temiz mesaj sınıflandırıcısı, benchmark ve araçları. Kendi gelen
> kutunuzdan veri toplayıp kişisel verileri maskeleyerek benzer bir benchmark kurmak için gereken her şey bu
> depoda.

## What's in here

| Step | Script | What it does |
|---|---|---|
| Collect | `import_iphone_backup.py` | reads SMS from an (encrypted) iPhone backup; skips outgoing, group and replied-to chats; masks immediately |
| | `import_sms_backup.py` | same for Android "SMS Backup & Restore" XML |
| Mask | `mask_pii.py` | phones, IBANs, Luhn-checked cards, checksum-validated TC IDs, e-mails, account numbers, plates, IPs, names after salutations / in transfer notices, and an optional `private_names.txt` (never committed) |
| Label | `label.py` | fast terminal labeller: template de-duplication, max 3 per sender, sender-based suggestions, review mode for LLM suggestions (`<out>.claude.jsonl`) |
| Check | `validate_dataset.py` | schema, enums, leftover personal data, duplicates |
| | `split_real.py` | dev/test split by sender |
| Train data | `gen_train.py` | 190 hand-written templates × slot filling → ~8k Turkish messages; personal details injected into legit *and* fraud equally |
| | `check_leakage.py` | drops training messages too similar (Jaccard ≥ 0.5) to any evaluation message |
| | `build_english.py` | UCI SMS Spam replay/eval halves (spam vs fraud distilled from the base model) |
| Train | `train.py` | fine-tune with frozen embeddings, bf16; fits a 6 GB GPU |
| Evaluate | `compare.py` | base vs. your checkpoints on every set, incl. contrast-pair accuracy; `--split dev/test` |
| | `sweep.py` | threshold sweep on dev data only |
| Release | `make_release.py` | builds the Hugging Face folders and re-scans everything for personal data |

Data schema and labelling guide: [DATASET.md](DATASET.md). Design notes: [FINETUNE_PLAN.md](FINETUNE_PLAN.md).

## Quick start

```bash
pip install -r requirements.txt
python test_mask_pii.py                      # masking tests
python import_iphone_backup.py data/candidates.jsonl
python label.py data/candidates.jsonl data/real_tr.jsonl
python gen_train.py data/train_synth.jsonl && python check_leakage.py data/train_synth.jsonl --drop
python train.py data/train_synth.jsonl --out checkpoints/my-model
python compare.py checkpoints/my-model --split dev
```

## Privacy

Nothing personal is in this repository: `data/`, `private_names.txt`, checkpoints and result CSVs are
excluded by a whitelist `.gitignore`. Raw messages are masked at import time and never written unmasked.

## License

Code: Apache-2.0. Model: Apache-2.0 (derived from Horizon-Labs/phishing-scam-detector-base, Apache-2.0, and
jhu-clsp/mmBERT-base, MIT). Benchmark: CC BY 4.0.
