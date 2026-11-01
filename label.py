"""Aday mesajları terminalde hızlıca etiketler. Kaldığı yerden devam eder.

Kullanım:
    python label.py data/candidates.jsonl data/real_tr.jsonl

Her mesajda:
    f = fraud   s = spam   l = legitimate   a = belirsiz (etiket sorulur, ambiguous=true)
    x = atla (etiketlenmez)   e = metni düzelt (ör. maskelenmemiş isim)   q = kaydet ve çık
    Enter = öneriyi kabul et (aynı göndericiden daha önce etiketlediğin mesaj varsa gösterilir)

Onay modu: data/real_tr.claude.jsonl varsa her mesajda Claude'un önerisi gösterilir. Enter ile onaylanan
kayıtlara labeled_by="claude_onayli", elle etiketlenenlere labeled_by="insan" yazılır.

Aynı şablonun kopyaları (sadece tutar, tarih, kod, link farklı) tek mesaj olarak gösterilir;
etiketli bir mesajla aynı şablondaki adaylar hiç gösterilmez.
"""
import json
import re
import sys
from pathlib import Path

from scam_schema import CATEGORIES, CHANNELS, DIFFICULTIES, HARD_TAGS

LABEL_KEYS = {"f": "fraud", "s": "spam", "l": "legitimate"}
SUGGESTED_FIELDS = ("label", "category", "difficulty", "hard_tags", "ambiguous")
SAME_TEMPLATE = 0.5  # kelime kümesi benzerliği (Jaccard) bu eşiği geçerse aynı şablon sayılır
PER_SENDER = 3  # bir kurumdan en fazla bu kadar mesaj; 40 tane aynı banka mesajı benchmark'ı çarpıtır
NAMED_SENDERS = ("alfanumerik", "eposta")  # göndericisi kurum adı olanlar: SMS başlığı ya da e-posta alan adı


def ask(prompt: str, valid=None, allow_empty=False) -> str:
    while True:
        ans = input(prompt).strip()
        if not ans and allow_empty:
            return ""
        if valid is None or ans in valid:
            return ans
        print(f"  Geçersiz. Seçenekler: {', '.join(valid)}")


def pick_from(name: str, options) -> str:
    print(f"  {name}: " + "  ".join(f"{i}={o}" for i, o in enumerate(options, 1)))
    idx = ask("  numara: ", [str(i) for i in range(1, len(options) + 1)])
    return options[int(idx) - 1]


def pick_many(name: str, options) -> list[str]:
    print(f"  {name} (virgülle, boş = yok): " + "  ".join(f"{i}={o}" for i, o in enumerate(options, 1)))
    while True:
        ans = input("  numaralar: ").strip()
        if not ans:
            return []
        try:
            return [options[int(x) - 1] for x in ans.split(",")]
        except (ValueError, IndexError):
            print("  Geçersiz, tekrar dene.")


def template_tokens(text: str) -> frozenset:
    t = text.lower()
    t = re.sub(r"\S*(?:https?://|www\.|\.com|\.net|\.org|\.tr|\.io|\.im|\.ly|\.co)\S*", " url ", t)
    t = re.sub(r"\d+", "0", t)
    return frozenset(re.findall(r"\w+", t))


def same_template(a: frozenset, b: frozenset) -> bool:
    return bool(a or b) and len(a & b) / len(a | b) >= SAME_TEMPLATE


def bucket(rec) -> str:
    # Kurum göndericisinde şablonlar göndericiye özgü; numaralar ise zaten anonim
    return rec["sender"] if rec.get("sender_type") in NAMED_SENDERS else rec.get("sender_type", "")


def suggestion_key(rec):
    return rec["sender"] if rec.get("sender_type") in NAMED_SENDERS else None


def describe(s: dict) -> str:
    tags = ", ".join(s.get("hard_tags", [])) or "-"
    amb = " · belirsiz" if s.get("ambiguous") else ""
    return f"{s['label']} · {s['category']} · {s['difficulty']} · [{tags}]{amb}"


def build_queue(candidates, labeled, done):
    """Gösterilecek mesajları sırasıyla, gizlenen kopya ve sınır aşımı sayılarıyla döndürür."""
    # Etiketli ve atlanmış mesajlar şablon temsilcisi olur; onlara benzeyen adaylar gösterilmez
    reps = {}
    by_id = {c["id"]: c for c in candidates}
    labeled_ids = {r["id"] for r in labeled}
    for r in labeled + [by_id[i] for i in done if i in by_id and i not in labeled_ids]:
        reps.setdefault(bucket(r), []).append(template_tokens(r["text"]))
    per_sender = {b: sum(1 for r in labeled if bucket(r) == b) for b in reps}
    fresh, copies, capped = {}, 0, 0
    for c in candidates:
        if c["id"] in done:
            continue
        b = bucket(c)
        tokens = template_tokens(c["text"])
        # Elle yazılmış setlerde karşıt çiftler (sahte ↔ gerçek) bilerek birbirine benzer; elenmezler
        if not c.get("is_synthetic") and any(same_template(tokens, t) for t in reps.get(b, [])):
            copies += 1
            continue
        reps.setdefault(b, []).append(tokens)
        if c.get("sender_type") in NAMED_SENDERS and per_sender.get(b, 0) >= PER_SENDER:
            capped += 1
            continue
        per_sender[b] = per_sender.get(b, 0) + 1
        fresh.setdefault(b, []).append(c)

    # Bilinmeyen numaralar ve kısa kodlar önce: dolandırıcılık en çok oradan gelir.
    # Kurumlar sırayla karışık gelir; ilk 100 mesajda bile çok sayıda farklı kurum görülsün.
    todo = [c for b in ("numara", "bilinmiyor", "kisa_kod") for c in fresh.pop(b, [])]
    queues = list(fresh.values())
    while queues:
        todo += [q.pop(0) for q in queues]
        queues = [q for q in queues if q]
    return todo, copies, capped


def main():
    if len(sys.argv) != 3:
        sys.exit("Kullanım: python label.py adaylar.jsonl cikti.jsonl")
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    sys.stdout.reconfigure(encoding="utf-8")

    candidates = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    labeled = []
    if dst.exists():
        labeled = [json.loads(l) for l in dst.read_text(encoding="utf-8").splitlines() if l.strip()]
    done = {r["id"] for r in labeled}
    skipped_path = dst.with_suffix(".skipped")
    if skipped_path.exists():
        done |= set(skipped_path.read_text(encoding="utf-8").split())

    # Onay modu: Claude'un önerileri <cikti>.claude.jsonl dosyasındaysa her mesajda gösterilir
    claude_path = dst.with_suffix(".claude.jsonl")
    claude_suggestions = {}
    if claude_path.exists():
        for l in claude_path.read_text(encoding="utf-8").splitlines():
            if l.strip():
                s = json.loads(l)
                claude_suggestions[s.pop("id")] = s
        print(f"Onay modu: {len(claude_suggestions)} Claude önerisi yüklendi ({claude_path}).")

    suggestions = {}
    for r in labeled:
        if suggestion_key(r):
            suggestions[suggestion_key(r)] = {k: r[k] for k in SUGGESTED_FIELDS if k in r}

    todo, copies, capped = build_queue(candidates, labeled, done)
    print(f"{len(todo)} mesaj etiketlenecek. {len(done)} tanesi daha önce yapılmış; {copies} tanesi aynı "
          f"şablonun kopyası, {capped} tanesi kurum başına {PER_SENDER} sınırını aştığı için gösterilmeyecek.\n")

    with dst.open("a", encoding="utf-8") as out, skipped_path.open("a", encoding="utf-8") as skipped:
        for i, rec in enumerate(todo, 1):
            print("─" * 70)
            print(f"[{i}/{len(todo)}]  gönderen: {rec.get('sender', '-')}")
            print(f"\n  {rec['text']}\n")
            claude = claude_suggestions.get(rec["id"])
            suggestion = claude or suggestions.get(suggestion_key(rec))
            if claude:
                print(f"  Claude: {describe(claude)}   (Enter = onayla)")
                if claude.get("explanation"):
                    print(f"          {claude['explanation']}")
            elif suggestion:
                print(f"  Öneri: {describe(suggestion)}   (Enter = kabul)")
            key = ask("Etiket [f/s/l/a/x/e/q]: ", ["f", "s", "l", "a", "x", "e", "q"], allow_empty=bool(suggestion))
            if key == "q":
                break
            if key == "x":
                skipped.write(rec["id"] + "\n")
                skipped.flush()
                continue
            if key == "e":
                rec["text"] = input("  Düzeltilmiş metin: ").strip() or rec["text"]
                key = ask("Etiket [f/s/l/a]: ", ["f", "s", "l", "a"], allow_empty=bool(suggestion))

            accepted_claude = key == "" and bool(claude)
            rec["labeled_by"] = "claude_onayli" if accepted_claude else "insan"
            if key == "":
                rec.update(suggestion)
            else:
                if key == "a":
                    rec["ambiguous"] = True
                    key = ask("  Yine de en olası etiket [f/s/l]: ", ["f", "s", "l"])
                rec["label"] = LABEL_KEYS[key]
                rec["category"] = pick_from("Kategori", CATEGORIES)
                rec["difficulty"] = pick_from("Zorluk", DIFFICULTIES)
                tags = pick_many("Zorluk etiketleri", HARD_TAGS)
                if tags:
                    rec["hard_tags"] = tags
            # DATASET.md: yasa dışı bahis reklamı her zaman belirsiz sayılır (Misli gibi lisanslılar spam olur)
            if rec["category"] == "bahis" and rec["label"] == "fraud":
                rec["ambiguous"] = True
                rec.setdefault("explanation", "Lisanssız bahis sitesi reklamı; bonus/kazanç vaadi ve kısaltılmış link.")
            if "channel" not in rec:  # setdefault kullanılmaz: soruyu her seferinde sorardı
                rec["channel"] = pick_from("Kanal", CHANNELS)
            if rec["label"] in ("fraud", "spam") and not (accepted_claude and rec.get("explanation")):
                expl = ask("  Neden? (boş geçilebilir): ", allow_empty=True)
                if expl:
                    rec["explanation"] = expl
            rec.setdefault("source", "kendi_gelen_kutusu")
            rec.setdefault("is_synthetic", False)

            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if suggestion_key(rec):
                suggestions[suggestion_key(rec)] = {k: rec[k] for k in SUGGESTED_FIELDS if k in rec}

    print(f"\nKaydedildi → {dst}")


if __name__ == "__main__":
    main()
