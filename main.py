from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient
import m3u8
from urllib.parse import urljoin, quote
import io
from aiocache import Cache, cached
import httpx

app = FastAPI()

# cors shi
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

http_client = AsyncClient()

# cache config
cache = Cache(Cache.MEMORY)

async def fetch_url(url: str) -> bytes:
    response = await http_client.get(url)
    response.raise_for_status()
    return response.content

def modify_m3u8_content(base_url: str, content: str) -> str:
    playlist = m3u8.loads(content)
    for segment in playlist.segments:
        original_url = segment.uri
        full_url = urljoin(base_url, original_url)
        proxy_url = f"/proxy?url={quote(full_url, safe='')}"
        segment.uri = proxy_url

    for key in playlist.keys:
        if key:
            original_url = key.uri
            full_url = urljoin(base_url, original_url)
            proxy_url = f"/proxy?url={quote(full_url, safe='')}"
            key.uri = proxy_url

    for playlist_variant in playlist.playlists:
        original_url = playlist_variant.uri
        full_url = urljoin(base_url, original_url)
        proxy_url = f"/proxy?url={quote(full_url, safe='')}"
        playlist_variant.uri = proxy_url

    return playlist.dumps()

@cached(ttl=300)  # cache for 5 mins incase repeated reqs
async def get_modified_m3u8(url: str) -> str:
    content = await fetch_url(url)
    base_url = url.rsplit("/", 1)[0] + "/"
    return modify_m3u8_content(base_url, content.decode("utf-8"))

@app.get("/proxy")
async def proxy(request: Request, url: str):
    try:
        if url.endswith(".m3u8"):
            modified_content = await get_modified_m3u8(url)
            return Response(content=modified_content, media_type="application/vnd.apple.mpegurl")
        else:
            content = await fetch_url(url)
            return StreamingResponse(io.BytesIO(content), media_type="video/MP2T")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.get("/")
async def root():
    return {"message": "M3U8 Proxy Server"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
