import os, re, hashlib
from datetime import datetime
from urllib.parse import quote_plus, urljoin
import httpx
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from selectolax.parser import HTMLParser
from dateutil import parser as dparser

app = FastAPI()

# Ustawimy to w Railway (adres strony wyników; {q} = fraza)
SEARCH_URL_TEMPLATE = os.getenv("SEARCH_URL_TEMPLATE", "")
API_TOKEN = os.getenv("API_TOKEN", "")

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})")

class SearchReq(BaseModel):
    q: str = Field(..., description="fraza, np. 'fundacja rodzinna'")
    date_from: str | None = Field(None, description="YYYY-MM-DD")
    limit: int = Field(10, ge=1, le=50)

def normalize_date(s: str):
    m = DATE_RE.search(s or "")
    if not m: return None
    try:
        dt = dparser.parse(m.group(1), dayfirst=True, fuzzy=True)
        return dt.date().isoformat()
    except Exception:
        return None

def extract_results(html: str, base: str):
    doc = HTMLParser(html)
    out = []
    for a in doc.css('a[href]'):
        href = a.attributes.get('href','')
        text = (a.text() or '').strip()
        if not href or not text: 
            continue
        # heurystyka: linki do podglądu interpretacji
        if "/informacje/podglad/" not in href and "interpret" not in href.lower():
            continue
        url = urljoin(base, href)
        # kontekst w okolicy linku
        block = a.parent
        ctx = block.text(separator=" ", strip=True) if block else text
        date = normalize_date(ctx)
        snippet = " ".join(ctx.split())[:240]
        item = {"title": text, "url": url, "date": date, "snippet": snippet}
        if not any(x["url"] == url for x in out):
            out.append(item)
    # limit i hash
    res = out[:50]
    for it in res:
        it["id"] = hashlib.md5((it["url"] + (it.get("date") or "")).encode("utf-8")).hexdigest()
    return res

@app.post("/eureka_search")
async def eureka_search(req: SearchReq, authorization: str = Header(default="")):
    if API_TOKEN and authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(401, "unauthorized")
    if not SEARCH_URL_TEMPLATE or "{q}" not in SEARCH_URL_TEMPLATE:
        raise HTTPException(500, "SEARCH_URL_TEMPLATE not configured")

    url = SEARCH_URL_TEMPLATE.format(q=quote_plus(req.q.strip()))
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent":"eureka-bot/1.0"}) as client:
        r = await client.get(url)
        if r.status_code != 200:
            raise HTTPException(502, f"search status {r.status_code}")
        items = extract_results(r.text, str(r.url))

    # filtr po dacie
    if req.date_from:
        try:
            df = datetime.strptime(req.date_from, "%Y-%m-%d").date()
            items = [x for x in items if x.get("date") and datetime.strptime(x["date"], "%Y-%m-%d").date() >= df]
        except ValueError:
            pass

    items = items[:req.limit]
    return {"count": len(items), "results": items}
