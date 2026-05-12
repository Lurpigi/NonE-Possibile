FROM python:3.12-slim

# Installa ffmpeg e Deno (runtime JS raccomandato per yt-dlp EJS)
# Deno è necessario dal 2025-11 per risolvere il "n challenge" di YouTube
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Installa Deno (runtime consigliato dalla wiki ufficiale di yt-dlp)
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh
RUN deno --version

# Installa yt-dlp via pip con [default] che include yt-dlp-ejs (gli EJS scripts)
# Il binario standalone da GitHub NON include gli EJS scripts → non funziona
RUN pip install "yt-dlp[default]" --no-cache-dir
RUN yt-dlp --version

WORKDIR /app
COPY search_subtitles.py .

ENV PYTHONUNBUFFERED=1

VOLUME ["/output"]
ENTRYPOINT ["python", "search_subtitles.py"]