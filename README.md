# Non È Possibile — Archivio SabakuNoMono

Archivio automatico di ogni volta che Sabaku ha detto *«non è possibile»* nei suoi video YouTube.
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

## Setup iniziale (una tantum)

### 1. Crea la repo GitHub

```bash
# Crea una repo pubblica su github.com, poi:
git init
git remote add origin https://github.com/TUOUSERNAME/TUOREPO.git
```

### 2. Sostituisci i placeholder nel codice

Cerca e sostituisci in `docs/index.html`:
- `TUOUSERNAME` → il tuo username GitHub
- `TUOREPO`     → il nome della tua repo

### 3. Primo commit

```bash
git add .
git commit -m "init: setup progetto"
git push -u origin main
```

### 4. Abilita GitHub Pages

1. Vai su **Settings → Pages** nella tua repo
2. Source: **Deploy from a branch**
3. Branch: `main` | Folder: `/docs`
4. Salva → il sito sarà online in ~1 minuto

Il sito sarà su: `https://TUOUSERNAME.github.io/TUOREPO/`

### 5. Abilita i permessi della Action

Vai su **Settings → Actions → General → Workflow permissions**
e seleziona **Read and write permissions** (serve per la push automatica).

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

## Strategia consigliata per il primo popolamento

Il canale di Sabaku ha molti video: scaricarli tutti in una notte con la
GitHub Action potrebbe essere bloccato prima della fine.

**Approccio consigliato:**

1. Fai girare Docker **in locale** (o su una VPS) la prima volta:
   ```bash
   docker compose up --build
   ```
   Lascia girare finché non finisce (ore). Se si blocca, rilancia:
   `docker compose up` riprende dai video mancanti.

2. Quando hai `output/results_cumulative.json` e `output/analyzed_videos.json`
   completi, committali nel repo:
   ```bash
   git add output/results_cumulative.json output/analyzed_videos.json
   cp output/results_cumulative.json docs/results.json
   git add docs/results.json
   git commit -m "feat: primo popolamento completo"
   git push
   ```

3. Da questo momento la GitHub Action notturna scaricherà solo i nuovi
   video pubblicati (in genere 1-5 al giorno) senza problemi.

---

## Output prodotti

| File | Descrizione |
|------|-------------|
| `output/results_cumulative.json` | Tutti i risultati trovati, formato JSON |
| `output/analyzed_videos.json` | ID di tutti i video già analizzati |
| `docs/results.json` | Copia del JSON per GitHub Pages |
| `output/subtitles/*.vtt` | Sottotitoli grezzi (non committati) |

### Struttura di ogni risultato JSON

```json
{
  "video_id":   "abc123XYZ01",
  "title":      "Titolo del video",
  "url":        "https://youtube.com/watch?v=abc123XYZ01",
  "timestamp":  "00:14:32",
  "start_sec":  872.5,
  "direct_url": "https://youtube.com/watch?v=abc123XYZ01&t=872s",
  "text":       "non è possibile Mi vien da piangere"
}
```

---

## Variabili d'ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `CHANNEL_URL` | `https://www.youtube.com/@SabakuNoStreamer` | Canale da scansionare |
| `SEARCH_PHRASE` | `non è possibile` | Frase da cercare |
| `LANG_CODE` | `it` | Lingua sottotitoli |
| `OUTPUT_DIR` | `/output` | Cartella output (nel container) |
