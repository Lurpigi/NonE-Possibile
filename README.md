# Non È Possibile - SabakuNoSutoriimaa

Archivio automatico di ogni volta che Sabaku ha detto _«non è possibile»_ nei suoi video YouTube.
Il sito si aggiorna ogni notte tramite GitHub Actions.

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
│   ├── results_cumulative.json # UNICA fonte di verità dei risultati
│   ├── analyzed_videos.json    # lista video già analizzati (skip logic)
│   └── subtitles/              # .vtt grezzi (NON committati, vedi .gitignore)
├── Dockerfile
├── docker-compose.yml
├── search_subtitles.py
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

```bash
# Prima run (scarica tutto + analizza):
docker compose up --build

# Run successive (scarica solo nuovi + analizza solo nuovi):
docker compose up

# Solo analisi senza download:
docker compose run --rm yt-search --skip-download

# Cerca una frase diversa:
docker compose run --rm -e SEARCH_PHRASE="assolutamente no" yt-search --skip-download
```

I file `output/results_cumulative.json` e `output/analyzed_videos.json`
vengono aggiornati ad ogni run. Puoi committarli nel repo dopo la prima
grande run locale e partire da lì.

---

## Output prodotti

| File                             | Descrizione                             |
| -------------------------------- | --------------------------------------- |
| `output/results_cumulative.json` | Tutti i risultati trovati, formato JSON |
| `output/analyzed_videos.json`    | ID di tutti i video già analizzati      |
| `docs/results.json`              | Copia del JSON per GitHub Pages         |
| `output/subtitles/*.vtt`         | Sottotitoli grezzi (non committati)     |

### Struttura di ogni risultato JSON

```json
{
    "video_id": "abc123XYZ01",
    "title": "Titolo del video",
    "url": "https://youtube.com/watch?v=abc123XYZ01",
    "timestamp": "00:14:32",
    "start_sec": 872.5,
    "direct_url": "https://youtube.com/watch?v=abc123XYZ01&t=872s",
    "text": "non è possibile Mi vien da piangere"
}
```
