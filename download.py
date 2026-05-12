import json
import random
import os
import subprocess
from pathlib import Path

import yt_dlp


def download_clips(
    json_path,
    output_dir,
    num_clips=100,
    seed=42,
    cookies_path=None
):
    print("Caricamento del file JSON...")

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Errore nella lettura del JSON: {e}")
        return

    random.seed(seed)
    sample_size = min(num_clips, len(data))
    selected_entries = random.sample(data, sample_size)
    print(f"Selezionate {sample_size} clip (Seed: {seed}).")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = output_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    for i, entry in enumerate(selected_entries):

        video_id = entry.get('video_id')
        start_sec = float(entry.get('start_sec'))
        url = entry.get('url')

        if not video_id or not url:
            print(f"[{i+1}] Entry non valida, skip.")
            continue

        end_sec = start_sec + 10

        print(
            f"\n[{i+1}/{sample_size}] "
            f"Download clip: {video_id} "
            f"(da {start_sec:.2f}s a {end_sec:.2f}s)"
        )

        temp_template = str(temp_dir / f"{video_id}_full.%(ext)s")
        final_file = output_dir / f"{video_id}_{int(start_sec)}.mp4"

        if final_file.exists():
            print("Clip già esistente, skip.")
            continue

        # ── Cookie setup ──────────────────────────────────────
        cookie_opts = {}
        if cookies_path:
            if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 50:
                cookie_opts['cookiefile'] = cookies_path
            else:
                print(
                    f"ATTENZIONE: Cookie non valido o non trovato: {cookies_path}")

        # ── yt-dlp: download solo il segmento necessario ──────
        ydl_opts = {
            # Robust format fallback chain
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': temp_template,
            'merge_output_format': 'mp4',
            'noplaylist': True,

            # Download only the 10s window — avoids fetching the full video
            'download_ranges': yt_dlp.utils.download_range_func(
                None, [(start_sec, end_sec)]
            ),
            'force_keyframes_at_cuts': True,  # more accurate cuts

            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'web_embedded', 'mweb']
                }
            },

            'quiet': False,
            'no_warnings': True,
            **cookie_opts,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            print(f"Errore download video {video_id}:\n{e}")
            continue

        # ── Find downloaded file ──────────────────────────────
        downloaded_files = list(temp_dir.glob(f"{video_id}_full.*"))
        if not downloaded_files:
            print("File scaricato non trovato.")
            continue

        downloaded_file = downloaded_files[0]

       # ── Find downloaded file ──────────────────────────────
        downloaded_files = list(temp_dir.glob(f"{video_id}_full.*"))
        if not downloaded_files:
            print("File scaricato non trovato.")
            continue

        downloaded_file = downloaded_files[0]

        # ── Sposta il file (yt-dlp lo ha già tagliato!) ───────
        print("Spostamento della clip pronta...")
        try:
            import shutil
            shutil.move(str(downloaded_file), str(final_file))
            print(f"Clip salvata: {final_file.name}")
        except Exception as e:
            print(f"Errore nello spostamento del file: {e}")
            continue

    print("\n--- Processo completato! ---")


if __name__ == "__main__":
    FILE_JSON = "./docs/results.json"
    CARTELLA_OUTPUT = "./clip"
    FILE_COOKIE = "./yt_cookies.txt"
    NUMERO_CLIP = 100
    SEED_CASUALE = 42

    download_clips(
        json_path=FILE_JSON,
        output_dir=CARTELLA_OUTPUT,
        num_clips=NUMERO_CLIP,
        seed=SEED_CASUALE,
        cookies_path=FILE_COOKIE
    )
