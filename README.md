# Aura (PWA per iPhone)

Tutti i file stanno nella radice del repository (nessuna cartella).

## 1. Pubblica la PWA su GitHub Pages
1. Carica tutti i file nella branch `main`.
2. Repository -> Settings -> Pages -> Source: *Deploy from a branch* -> `main` / `(root)` -> Save.
3. Indirizzo risultante: `https://TUOUTENTE.github.io/NOMEREPO/`

## 2. Avvia il server (serve per ricerca e audio)
GitHub non puo eseguire Python: il server gira su un tuo PC / Raspberry / VPS.

    pip install -r requirements.txt
    export AURA_KEY=una-chiave-segreta          # Windows: set AURA_KEY=...
    export AURA_ORIGIN=https://TUOUTENTE.github.io
    uvicorn server:app --host 0.0.0.0 --port 8000

Rendilo raggiungibile in HTTPS (obbligatorio, la PWA e in HTTPS):
`cloudflared tunnel --url http://localhost:8000`  ->  `https://xxxx.trycloudflare.com`

## 3. iPhone
Safari -> apri l'indirizzo GitHub Pages -> Condividi -> Aggiungi a Home.
Al primo avvio l'app chiede l'indirizzo del server (quello https) e la chiave AURA_KEY.
Modificabili in seguito da Impostazioni -> Server.

## Note
- Non pubblicare mai la chiave AURA_KEY nel repository.
- Se lo streaming smette di funzionare: `pip install -U yt-dlp` (meglio con `deno` o `node` installato).
- Il volume su iOS si regola solo con i tasti fisici.
