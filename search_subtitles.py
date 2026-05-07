#!/usr/bin/env python3
"""
YouTube Subtitle Searcher v3
- Scarica i sottotitoli automatici IT di tutti i video di un canale
- Salta i VTT già presenti su disco
- Gestisce correttamente la struttura "rolling window con overlap" di YT
- Aggiorna un JSON cumulativo (append-only sui nuovi video)
"""

import os
import re
import json
import csv
import subprocess
import argparse
from pathlib import Path

# ── Configurazione ───────────────────────────────────────────────────────────
CHANNEL_URL = os.getenv(
    "CHANNEL_URL",   "https://www.youtube.com/@SabakuNoStreamer")
SEARCH_PHRASE = os.getenv("SEARCH_PHRASE", "non è possibile")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/output"))
SUBS_DIR = OUTPUT_DIR / "subtitles"
LANG = os.getenv("LANG_CODE", "it")
CUMULATIVE_JSON = OUTPUT_DIR / "results_cumulative.json"
# Cookies: path a un file cookies.txt Netscape (opzionale, serve per GitHub Actions)
COOKIES_FILE = os.getenv("YT_COOKIES_FILE", "")
# ─────────────────────────────────────────────────────────────────────────────


# ── Utilità tempo ─────────────────────────────────────────────────────────────

def vtt_time_to_seconds(time_str: str) -> float:
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def seconds_to_hhmmss(seconds: float) -> str:
    t = int(seconds)
    return f"{t//3600:02d}:{(t % 3600)//60:02d}:{t % 60:02d}"


# ── Parsing VTT con deduplicazione rolling-window ────────────────────────────

def clean_vtt_text(raw: str) -> str:
    """Rimuove tag HTML/timing e normalizza spazi."""
    text = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", text).strip()


def parse_vtt_to_sentences(vtt_path: Path) -> list:
    """
    Ricostruisce frasi dal VTT auto-generato di YouTube.

    YT usa finestre scorrevoli con overlap:
      Finestra N:   "ABC DEF GHI"          (contiene nuove parole)
      Cue reset:    "GHI"                  (coda di N, ripetuta come inizio di N+1)
      Finestra N+1: "GHI JKL MNO"         (estende da GHI)

    Il cue di reset ("GHI") è già nel buffer → va riconosciuto e saltato
    senza emettere le sue parole una seconda volta.

    Risultato: ogni parola viene emessa UNA SOLA VOLTA, con il timestamp
    del momento in cui appare per la prima volta.
    """
    raw = vtt_path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"\AWEBVTT[^\n]*\n(.*?\n)?\n", "", raw)  # strip header

    cue_re = re.compile(
        r"(\d{2}:\d{2}:\d{2}[\.,]\d{3})\s*-->\s*\S+[^\n]*\n(.*?)(?=\n\n|\Z)",
        re.DOTALL,
    )

    raw_cues = [
        {"start": vtt_time_to_seconds(
            m.group(1)), "text": clean_vtt_text(m.group(2))}
        for m in cue_re.finditer(raw)
    ]

    sentences = []
    buf_words: list[str] = []
    buf_start: float | None = None
    prev_text: str = ""

    def flush(end: float):
        nonlocal buf_words, buf_start
        if buf_words:
            sentences.append({"start": buf_start, "end": end,
                              "text": " ".join(buf_words)})
        buf_words = []
        buf_start = None

    for cue in raw_cues:
        text = cue["text"]
        start = cue["start"]

        # ── Cue vuoto: reset esplicito ────────────────────────────────────
        if not text:
            flush(start)
            prev_text = ""
            continue

        # ── Estensione normale: testo corrente inizia con il precedente ───
        if prev_text and text.startswith(prev_text):
            new_part = text[len(prev_text):].strip()
            if new_part:
                if buf_start is None:
                    buf_start = start
                buf_words.extend(new_part.split())
            prev_text = text
            continue

        # ── Cue di transizione (overlap): il testo è la CODA del precedente
        # Esempi:
        #   prev = "ABC DEF GHI JKL"  →  cue = "GHI JKL"  (endswith)
        #   prev = "ABC DEF GHI JKL"  →  cue = "JKL"       (endswith)
        if prev_text and prev_text.endswith(text):
            # Già nel buffer: chiudi la frase corrente e usa questo testo
            # come nuovo "prev" per il prossimo extend
            flush(start)
            prev_text = text
            continue

        # Caso più generale: il testo di transizione è contenuto nel precedente
        if prev_text and text in prev_text:
            flush(start)
            prev_text = text
            continue

        # ── Reset vero: nuovo contenuto non correlato ─────────────────────
        flush(start)
        if text:
            buf_start = start
            buf_words = text.split()
        prev_text = text

    flush(float("inf"))
    return sentences


# ── Ricerca ───────────────────────────────────────────────────────────────────

def search_phrase(sentences: list, phrase: str) -> list:
    pl = phrase.lower()
    return [s for s in sentences if pl in s["text"].lower()]


# ── ID/titolo da path VTT ─────────────────────────────────────────────────────

def id_and_title(vtt_path: Path) -> tuple:
    stem = vtt_path.stem.removesuffix(f".{LANG}")
    m = re.search(r"\[([A-Za-z0-9_\-]{11})\]$", stem)
    if m:
        return m.group(1), stem[: m.start()].strip()
    return "unknown", stem


# ── Cookie helper ────────────────────────────────────────────────────────────

def cookies_args() -> list:
    """Restituisce i flag --cookies se il file è configurato e valido."""
    if COOKIES_FILE and Path(COOKIES_FILE).exists():
        size = Path(COOKIES_FILE).stat().st_size
        if size > 50:  # file non vuoto/placeholder
            print(f"[INFO] Uso cookies: {COOKIES_FILE} ({size} bytes)")
            return ["--cookies", COOKIES_FILE]
        else:
            print(
                f"[WARN] File cookies troppo piccolo ({size} bytes) — ignorato.")
    return []


# ── Download ──────────────────────────────────────────────────────────────────

def get_channel_ids() -> list:
    print("[yt-dlp] Recupero lista video dal canale...")
    r = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "id", "--ignore-errors",
         *cookies_args(), CHANNEL_URL],
        capture_output=True, text=True,
    )
    ids = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    print(f"[yt-dlp] {len(ids)} video trovati nel canale.")
    return ids


def download_subtitles():
    SUBS_DIR.mkdir(parents=True, exist_ok=True)

    already = {id_and_title(p)[0] for p in SUBS_DIR.glob(f"*.{LANG}.vtt")}
    if already:
        print(
            f"[SKIP] {len(already)} VTT già presenti su disco → non riscaricati.")

    all_ids = get_channel_ids()
    to_download = [v for v in all_ids if v not in already]
    print(f"[INFO] Nuovi video da scaricare: {len(to_download)}\n")

    if not to_download:
        print("[INFO] Nessun nuovo video — download saltato.")
        return

    batch = OUTPUT_DIR / "_batch.txt"
    batch.write_text(
        "\n".join(f"https://www.youtube.com/watch?v={v}" for v in to_download),
        encoding="utf-8",
    )

    subprocess.run([
        "yt-dlp",
        "--batch-file", str(batch),
        "--skip-download",          # non scaricare il video
        "--write-auto-sub",         # sottotitoli auto-generati
        "--sub-lang", LANG,
        "--sub-format", "vtt",
        # NON usiamo --convert-subs: richiederebbe un formato video disponibile
        # e causa "Requested format is not available" su alcuni video.
        # non verificare i formati video (non servono)
        "--no-check-formats",
        "--output", str(SUBS_DIR / "%(title)s [%(id)s].%(ext)s"),
        "--ignore-errors",
        "--sleep-interval", "1",
        *cookies_args(),
    ], text=True)

    batch.unlink(missing_ok=True)


# ── Analisi ───────────────────────────────────────────────────────────────────

def process_subtitles(phrase: str, already_done_ids: set) -> list:
    """
    Analizza solo i VTT non ancora presenti nel JSON cumulativo.
    Restituisce i nuovi risultati trovati.
    """
    vtt_files = sorted(SUBS_DIR.glob(f"*.{LANG}.vtt"))
    new_files = [p for p in vtt_files if id_and_title(
        p)[0] not in already_done_ids]
    skip_count = len(vtt_files) - len(new_files)

    print(
        f"\n[INFO] VTT totali: {len(vtt_files)} | già analizzati: {skip_count} | nuovi: {len(new_files)}")

    results = []
    for vtt_path in new_files:
        vid_id, title = id_and_title(vtt_path)
        url = f"https://www.youtube.com/watch?v={vid_id}"

        sentences = parse_vtt_to_sentences(vtt_path)
        hits = search_phrase(sentences, phrase)

        if hits:
            print(f"  ✓ [{title}] — {len(hits)} occorrenza/e")
            for h in hits:
                results.append({
                    "video_id": vid_id,
                    "title": title,
                    "url": url,
                    "timestamp": seconds_to_hhmmss(h["start"]),
                    "start_sec": round(h["start"], 2),
                    "direct_url": f"{url}&t={int(h['start'])}s",
                    "text": h["text"],
                })
        else:
            print(f"  · [{title}] — nessuna occorrenza")

    return results


# ── Salvataggio cumulativo ────────────────────────────────────────────────────

def load_cumulative() -> tuple:
    """Carica il JSON cumulativo. Restituisce (lista_risultati, set_video_id_analizzati)."""
    # Il JSON cumulativo tiene anche i video analizzati senza hit,
    # così da non rianalizzarli ogni volta.
    meta_path = OUTPUT_DIR / "analyzed_videos.json"

    results = []
    if CUMULATIVE_JSON.exists():
        results = json.loads(CUMULATIVE_JSON.read_text(encoding="utf-8"))

    analyzed = set()
    if meta_path.exists():
        analyzed = set(json.loads(meta_path.read_text(encoding="utf-8")))

    return results, analyzed, meta_path


def save_cumulative(all_results: list, analyzed_ids: set, meta_path: Path):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    CUMULATIVE_JSON.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    meta_path.write_text(
        json.dumps(sorted(analyzed_ids), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # CSV di comodo
    csv_path = OUTPUT_DIR / "results_cumulative.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["video_id", "title", "timestamp", "direct_url", "text"])
        w.writeheader()
        w.writerows({k: r[k] for k in ["video_id", "title",
                    "timestamp", "direct_url", "text"]} for r in all_results)

    print(f"\n[JSON] → {CUMULATIVE_JSON}")
    print(f"[CSV]  → {csv_path}")
    print(f"[META] → {meta_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-download", action="store_true",
                        help="Non scarica nuovi VTT, usa solo quelli presenti")
    parser.add_argument("--phrase", default=SEARCH_PHRASE)
    args = parser.parse_args()
    phrase = args.phrase

    print("=" * 50)
    print("  YouTube Subtitle Searcher  v3")
    print("=" * 50)
    print(f"Canale : {CHANNEL_URL}")
    print(f"Frase  : \"{phrase}\"")
    print(f"Output : {OUTPUT_DIR}\n")

    if not args.skip_download:
        download_subtitles()
    else:
        print("[INFO] Download saltato.")

    # Carica risultati e lista video già analizzati
    existing_results, analyzed_ids, meta_path = load_cumulative()
    print(
        f"[INFO] Risultati già nel JSON: {len(existing_results)} | Video già analizzati: {len(analyzed_ids)}")

    # Analizza solo i nuovi VTT
    new_results = process_subtitles(phrase, analyzed_ids)

    # Aggiorna il set dei video analizzati con tutti quelli ora su disco
    for vtt_path in SUBS_DIR.glob(f"*.{LANG}.vtt"):
        analyzed_ids.add(id_and_title(vtt_path)[0])

    # Merge
    all_results = existing_results + new_results

    save_cumulative(all_results, analyzed_ids, meta_path)

    print(f"\n✅ Totale occorrenze nel JSON cumulativo: {len(all_results)}")
    if new_results:
        uv = len({r["video_id"] for r in new_results})
        print(f"   Nuove questa run: {len(new_results)} in {uv} video.")
    else:
        print("   Nessuna nuova occorrenza trovata.")


if __name__ == "__main__":
    main()
