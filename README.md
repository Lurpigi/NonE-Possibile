# Non È Possibile - SabakuNoSutoriimaa

Archivio automatico di ogni volta che Sabaku ha detto _«non è possibile»_ nei suoi video YouTube.
Il sito si aggiorna ogni notte tramite GitHub Actions.

**Stato attuale:** 🎯 **1.844 risultati** trovati da **3.092 video** analizzati

## Struttura del progetto

```
.
├── .github/
│   └── workflows/
│       └── update.yml          # GitHub Action (aggiorna ogni notte)
├── docs/                       # GitHub Pages (sito pubblico)
│   ├── index.html              # sito web
│   └── results.json            # copia del JSON per il sito
├── output/                     # dati persistenti (committati)
│   ├── results_cumulative.json # UNICA fonte di verità dei risultati (1.844 match)
│   ├── analyzed_videos.json    # lista video già analizzati: 3.092 video
│   ├── failed_videos.json      # traccia i video che hanno fallito
│   └── subtitles/              # .vtt grezzi (NON committati, vedi .gitignore)
├── clip/                       # clip video scaricate
│   └── temp/                   # temp directory per ffmpeg
├── Dockerfile                  # immagine per search_subtitles.py
├── Dockerfile.download         # immagine per download.py
├── docker-compose.yml
├── search_subtitles.py         # script principale (analisi sottotitoli)
├── download.py                 # script per scaricare clip casuali
├── yt_cookies.txt              # cookies YouTube (non committati)
└── .gitignore
```

---

## Come funziona il ciclo di aggiornamento

```
Ogni notte (00:00 UTC)
        │
        ▼
  [yt-dlp] Lista video del canale
        │
        ▼
  Quali ID sono già in analyzed_videos.json?
        │
        ├─ già presenti → SKIP (non riscarica)
        │
        └─ nuovi → scarica .vtt
                │
                ▼
         Analizza solo i nuovi VTT
                │
                ▼
         Aggiunge risultati a results_cumulative.json
         Aggiorna analyzed_videos.json
         Copia in docs/results.json
                │
                ▼
         git commit + push
         (solo se ci sono cambiamenti)
```

**Perché `analyzed_videos.json`?**
Dopo qualche centinaia di video YouTube blocca temporaneamente l'IP.
Questo file ricorda quali video sono già stati scaricati e analizzati,
così le run successive scaricano solo i nuovi video (pochi al giorno).

---

## Uso locale (Docker)

### Analizzare i sottotitoli (ricerca di frasi)

```bash
# Prima run (scarica tutto + analizza):
docker compose up --build yt-search

# Run successive (scarica solo nuovi + analizza solo nuovi):
docker compose up yt-search

# Solo analisi senza download:
docker compose run --rm yt-search --skip-download

# Cerca una frase diversa:
docker compose run --rm -e SEARCH_PHRASE="assolutamente no" yt-search --skip-download
```

### Scaricare clip casuali

```bash
# Scarica 100 clip casuali (default) dai risultati:
docker compose run --rm downloader

# Scarica N clip specifiche:
docker compose run --rm -e NUM_CLIPS=50 downloader
```

I file `output/results_cumulative.json` e `output/analyzed_videos.json`
vengono aggiornati ad ogni run. Puoi committarli nel repo dopo la prima
grande run locale e partire da lì.

Le clip scaricate vengono salvate in `clip/` con gli ultimi 10 secondi
di ogni timestamp trovato.

---

## Output prodotti

| File                             | Descrizione                                             |
| -------------------------------- | ------------------------------------------------------- |
| `output/results_cumulative.json` | 1.844 risultati trovati, formato JSON (FONTE DI VERITÀ) |
| `output/analyzed_videos.json`    | ID di 3.092 video già analizzati (skip logic)           |
| `output/failed_videos.json`      | Traccia video che hanno fallito (per retry)             |
| `docs/results.json`              | Copia del JSON per GitHub Pages (sito pubblico)         |
| `output/subtitles/*.vtt`         | Sottotitoli grezzi scaricati (non committati)           |
| `clip/*.mp4`                     | Clip video scaricate (non committati)                   |

### Struttura di ogni risultato JSON

```json
{
    "video_id": "abc123XYZ01",
    "title": "Titolo del video",
    "upload_date": "data upload",
    "url": "https://youtube.com/watch?v=abc123XYZ01",
    "timestamp": "00:14:32",
    "start_sec": 872.5,
    "direct_url": "https://youtube.com/watch?v=abc123XYZ01&t=872s",
    "text": "non è possibile Mi vien da piangere"
}
```
