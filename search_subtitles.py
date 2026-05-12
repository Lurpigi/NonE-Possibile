#!/usr/bin/env python3
"""
YouTube Subtitle Searcher v5
- Scarica i sottotitoli automatici IT
- Deduplica le frasi (rolling window)
- Recupera in modo robusto le date di pubblicazione reali
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
    "CHANNEL_URL", "https://www.youtube.com/@SabakuNoStreamer")
SEARCH_PHRASE = os.getenv("SEARCH_PHRASE", "non è possibile")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/output"))
SUBS_DIR = OUTPUT_DIR / "subtitles"
LANG = os.getenv("LANG_CODE", "it")
CUMULATIVE_JSON = OUTPUT_DIR / "results_cumulative.json"
FAILED_JSON = OUTPUT_DIR / "failed_videos.json"
COOKIES_FILE = os.getenv("YT_COOKIES_FILE", "")
RETRY_FAILED = os.getenv("RETRY_FAILED", "false").lower() == "true"

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

# ── Parsing VTT ──────────────────────────────────────────────────────────────


def clean_vtt_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", text).strip()


def parse_vtt_to_sentences(vtt_path: Path) -> list:
    raw = vtt_path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"\AWEBVTT[^\n]*\n(.*?\n)?\n", "", raw)

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

        if not text:
            flush(start)
            prev_text = ""
            continue

        if prev_text and text.startswith(prev_text):
            new_part = text[len(prev_text):].strip()
            if new_part:
                if buf_start is None:
                    buf_start = start
                buf_words.extend(new_part.split())
            prev_text = text
            continue

        if prev_text and prev_text.endswith(text):
            flush(start)
            prev_text = text
            continue

        if prev_text and text in prev_text:
            flush(start)
            prev_text = text
            continue

        flush(start)
        if text:
            buf_start = start
            buf_words = text.split()
        prev_text = text

    flush(float("inf"))
    return sentences

# ── Helpers ──────────────────────────────────────────────────────────────────


def search_phrase(sentences: list, phrase: str) -> list:
    pl = phrase.lower()
    return [s for s in sentences if pl in s["text"].lower()]


def id_and_title(vtt_path: Path) -> tuple:
    stem = vtt_path.stem.removesuffix(f".{LANG}")
    m = re.search(r"\[([A-Za-z0-9_\-]{11})\]$", stem)
    if m:
        return m.group(1), stem[: m.start()].strip()
    return "unknown", stem


def cookies_args() -> list:
    if COOKIES_FILE and Path(COOKIES_FILE).exists():
        size = Path(COOKIES_FILE).stat().st_size
        if size > 50:
            return ["--cookies", COOKIES_FILE]
    return []

# ── Interrogazione YT ─────────────────────────────────────────────────────────


def get_channel_ids() -> list:
    print("[yt-dlp] Recupero lista video dal canale...")
    r = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "id", "--ignore-errors",
         "--extractor-args", "youtube:player_client=web,web_embedded,mweb",
         "--js-runtimes", "deno",
         *cookies_args(), CHANNEL_URL],
        capture_output=True, text=True,
    )
    ids = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    return ids


# ── Download ──────────────────────────────────────────────────────────────────


def load_failed_ids() -> set:
    if FAILED_JSON.exists():
        return set(json.loads(FAILED_JSON.read_text(encoding="utf-8")))
    return set()


def save_failed_ids(failed: set):
    FAILED_JSON.write_text(json.dumps(
        sorted(failed), ensure_ascii=False, indent=2), encoding="utf-8")


def download_subtitles(analyzed_ids: set, channel_ids: list):
    SUBS_DIR.mkdir(parents=True, exist_ok=True)
    failed_ids = load_failed_ids()
    if RETRY_FAILED and failed_ids:
        failed_ids = set()

    already = set(analyzed_ids) | failed_ids
    on_disk = {id_and_title(p)[0] for p in SUBS_DIR.glob(f"*.{LANG}.vtt")}
    already |= on_disk

    to_download = [v for v in channel_ids if v not in already]
    print(f"[INFO] Nuovi video da scaricare: {len(to_download)}\n")

    if not to_download:
        return

    batch = OUTPUT_DIR / "_batch.txt"
    batch.write_text("\n".join(
        f"https://www.youtube.com/watch?v={v}" for v in to_download), encoding="utf-8")

    subprocess.run([
        "yt-dlp", "--batch-file", str(
            batch), "--skip-download", "--write-auto-sub", "--write-info-json",
        "--sub-lang", LANG, "--sub-format", "vtt", "--no-check-formats",
        "--extractor-args", "youtube:player_client=web,web_embedded,mweb",
        "--js-runtimes", "deno", "--output", str(
            SUBS_DIR / "%(title)s [%(id)s].%(ext)s"),
        "--ignore-errors", "--sleep-interval", "2", "--max-sleep-interval", "5",
        "--sleep-subtitles", "1", *cookies_args(),
    ], text=True)
    batch.unlink(missing_ok=True)

    after_download = {id_and_title(p)[0]
                      for p in SUBS_DIR.glob(f"*.{LANG}.vtt")}
    newly_failed = {v for v in to_download if v not in (
        after_download - on_disk)}

    if newly_failed:
        save_failed_ids(load_failed_ids() | newly_failed)
    elif RETRY_FAILED:
        save_failed_ids(set())

# ── Analisi ───────────────────────────────────────────────────────────────────


def load_info_json(vtt_path: Path) -> dict:
    info_path = vtt_path.with_suffix("").with_suffix(".info.json")

    if not info_path.exists():
        return {}

    try:
        return json.loads(info_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def process_subtitles(phrase: str, new_files: list, video_dates: dict) -> list:
    results = []
    for vtt_path in new_files:
        vid_id, title = id_and_title(vtt_path)
        url = f"https://www.youtube.com/watch?v={vid_id}"

        # Prendiamo la data recuperata, o usiamo un fallback evidente
        info = load_info_json(vtt_path)

        raw_date = info.get("upload_date", "")
        if raw_date and len(raw_date) == 8:
            upload_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        else:
            upload_date = "1970-01-01"

        sentences = parse_vtt_to_sentences(vtt_path)
        hits = search_phrase(sentences, phrase)

        if hits:
            print(f"  ✓ [{title}] ({upload_date}) — {len(hits)} occorrenza/e")
            for h in hits:
                results.append({
                    "video_id": vid_id,
                    "title": title,
                    "upload_date": upload_date,
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
    meta_path = OUTPUT_DIR / "analyzed_videos.json"
    results = json.loads(CUMULATIVE_JSON.read_text(
        encoding="utf-8")) if CUMULATIVE_JSON.exists() else []
    analyzed = set(json.loads(meta_path.read_text(
        encoding="utf-8"))) if meta_path.exists() else set()
    return results, analyzed, meta_path


def save_cumulative(all_results: list, analyzed_ids: set, meta_path: Path):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CUMULATIVE_JSON.write_text(json.dumps(
        all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps(sorted(analyzed_ids),
                         ensure_ascii=False, indent=2), encoding="utf-8")

# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--phrase", default=SEARCH_PHRASE)
    args = parser.parse_args()

    existing_results, analyzed_ids, meta_path = load_cumulative()

    if not args.skip_download:
        channel_ids = get_channel_ids()
        download_subtitles(analyzed_ids, channel_ids)
    else:
        print("[INFO] Download saltato.")

    # Trova i VTT da analizzare
    vtt_files = sorted(SUBS_DIR.glob(f"*.{LANG}.vtt"))

    new_files = [
        p for p in vtt_files
        if id_and_title(p)[0] not in analyzed_ids
    ]

    # Analizza direttamente i file
    new_results = process_subtitles(args.phrase, new_files)

    # Marca i video come analizzati
    for p in new_files:
        analyzed_ids.add(id_and_title(p)[0])

    # Merge risultati
    all_results = existing_results + new_results

    save_cumulative(all_results, analyzed_ids, meta_path)

    print("\n✅ Operazione conclusa.")


if __name__ == "__main__":
    main()
