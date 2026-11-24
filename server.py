"""Aura PWA server: ricerca + proxy audio (con Range) via yt-dlp. Serve anche la PWA in /web."""
import asyncio, os, re, shutil, time
from pathlib import Path
from urllib.parse import quote

import httpx, yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

KEY = os.getenv("AURA_KEY", "")          # consigliato: protegge le API
app = FastAPI()
cache: dict = {}                          # id -> (scadenza, url, headers, titolo, ext)


def opts() -> dict:
    o = {"quiet": True, "no_warnings": True, "noplaylist": True}
    rt = {n: {"path": p} for n in ("deno", "node", "bun", "quickjs") if (p := shutil.which(n))}
    if rt:
        o["js_runtimes"] = rt
    return o


def resolve(vid: str):
    c = cache.get(vid)
    if c and c[0] > time.time():
        return c
    o = opts() | {"format": "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio"}  # m4a = AAC, compatibile con iOS
    with yt_dlp.YoutubeDL(o) as y:
        i = y.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    c = (time.time() + 3 * 3600, i["url"], i.get("http_headers", {}), i.get("title", vid), i.get("ext", "m4a"))
    cache[vid] = c
    return c


@app.middleware("http")
async def auth(req: Request, call_next):
    if KEY and req.url.path.startswith("/api/") and req.query_params.get("k") != KEY:
        return JSONResponse({"error": "unauthorized"}, 401)
    return await call_next(req)


# CORS: la PWA su GitHub Pages (altro dominio) deve poter chiamare questo server.
# Restringi con AURA_ORIGIN=https://TUOUTENTE.github.io (separati da virgola); di default accetta tutti.
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("AURA_ORIGIN", "*").split(","),
                   allow_methods=["GET"], allow_headers=["*"])


@app.get("/api/search")
def search(q: str, n: int = 25):
    o = opts() | {"extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(o) as y:
        info = y.extract_info(f"ytsearch{min(n, 40)}:{q}", download=False)
    return [
        {"id": e["id"], "title": e.get("title") or e["id"], "artist": e.get("uploader") or e.get("channel") or "",
         "dur": int(e.get("duration") or 0)}
        for e in (info or {}).get("entries", []) if e.get("id") and len(e["id"]) == 11
    ]


@app.get("/api/radio/{vid}")
def radio(vid: str, n: int = 25):
    """Radio / brani simili: usa la 'mix' automatica di YouTube per quel video."""
    if not re.fullmatch(r"[\w-]{11}", vid):
        raise HTTPException(400)
    o = opts() | {"extract_flat": True, "skip_download": True, "noplaylist": False, "playlistend": n}
    with yt_dlp.YoutubeDL(o) as y:
        info = y.extract_info(f"https://www.youtube.com/watch?v={vid}&list=RD{vid}", download=False)
    return [
        {"id": e["id"], "title": e.get("title") or e["id"], "artist": e.get("uploader") or e.get("channel") or "",
         "dur": int(e.get("duration") or 0)}
        for e in (info or {}).get("entries", []) if e.get("id") and len(e["id"]) == 11
    ]


@app.get("/api/warm/{vid}")
def warm(vid: str):
    """Pre-risolve il brano successivo: il cambio traccia in background resta istantaneo."""
    if not re.fullmatch(r"[\w-]{11}", vid):
        raise HTTPException(400)
    resolve(vid)
    return {"ok": True}


@app.get("/api/stream/{vid}")
async def stream(vid: str, request: Request, dl: int = 0):
    if not re.fullmatch(r"[\w-]{11}", vid):
        raise HTTPException(400)
    for attempt in (0, 1):
        _, url, hdr, title, ext = await asyncio.to_thread(resolve, vid)
        h = dict(hdr)
        if "range" in request.headers:
            h["Range"] = request.headers["range"]
        client = httpx.AsyncClient(timeout=None, follow_redirects=True)
        r = await client.send(client.build_request("GET", url, headers=h), stream=True)
        if r.status_code < 400:
            break
        await r.aclose(); await client.aclose(); cache.pop(vid, None)   # URL scaduto: ririsolvi
        if attempt:
            raise HTTPException(502, "upstream")
    out = {k: r.headers[k] for k in ("content-length", "content-range") if k in r.headers}
    out["Accept-Ranges"] = "bytes"
    out["Cache-Control"] = "no-store"
    if dl:
        out["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(title)}.{ext}"

    async def gen():
        try:
            async for ch in r.aiter_raw():
                yield ch
        finally:
            await r.aclose(); await client.aclose()

    return StreamingResponse(gen(), status_code=r.status_code, headers=out,
                             media_type="audio/mp4" if ext == "m4a" else f"audio/{ext}")


ROOT = Path(__file__).parent
PUBLIC = {"index.html", "sw.js", "manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "logo.png"}


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/{name}")
def public(name: str):      # opzionale: serve la PWA anche da qui (solo i file elencati)
    if name not in PUBLIC:
        raise HTTPException(404)
    return FileResponse(ROOT / name)
