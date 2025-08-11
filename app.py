import os, hashlib
from typing import List
from fastapi import FastAPI, HTTPException, Header, Query
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright

app = FastAPI()

# --------- MODELE ----------
class SearchReq(BaseModel):
    q: str = Field(..., description="fraza, np. 'fundacja rodzinna'")
    limit: int = Field(5, ge=1, le=20)

class Item(BaseModel):
    title: str
    url: str

class Resp(BaseModel):
    count: int
    results: List[Item]

# --------- PING ------------
@app.get("/ping")
async def ping():
    return {"ok": True}

# --------- WSPÓLNA LOGIKA ---------
async def do_search(query: str, limit: int) -> Resp:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(locale="pl-PL")
        page = await context.new_page()

        await page.goto("https://eureka.mf.gov.pl/", wait_until="domcontentloaded")

        # pole wyszukiwania – kilka możliwych selektorów
        selectors = [
            'input[type="search"]',
            'input[placeholder*="fra"]',
            'input[aria-label*="zuk"]',
            'input[aria-label*="szuk"]'
        ]
        found = False
        for sel in selectors:
            if await page.locator(sel).first().count():
                await page.locator(sel).first().fill(query)
                found = True
                break
        if not found:
            await browser.close()
            raise HTTPException(502, "search box not found")

        # klik „Szukaj”
        btn = page.locator('button:has-text("Szukaj"), input[type="submit"]')
        await btn.first().click()

        # poczekaj na wyniki i zbierz linki do podglądu interpretacji
        await page.wait_for_load_state("networkidle")
        await page.wait_for_selector('a[href*="/informacje/podglad/"]', timeout=25000)
        links = page.locator('a[href*="/informacje/podglad/"]')
        n = await links.count()

        out = []
        for i in range(min(n, limit)):
            href = await links.nth(i).get_attribute("href")
            title = (await links.nth(i).inner_text()).strip()
            if not href:
                continue
            url = href if href.startswith("http") else page.url.split("/szukaj")[0] + href
            if not any(x["url"] == url for x in out):
                out.append({"title": title or "Interpretacja", "url": url})

        await context.close()
        await browser.close()
        return {"count": len(out), "results": out}

# --------- AUTORYZACJA ---------
def check_auth(authorization: str, token_qparam: str | None):
    token_env = os.getenv("API_TOKEN", "")
    # pozwalamy albo na nagłówek, albo na ?token= dla łatwego testu w przeglądarce
    if token_env:
        if authorization == f"Bearer {token_env}":
            return
        if token_qparam == token_env:
            return
        raise HTTPException(401, "unauthorized")

# --------- ENDPOINTY GET/POST ---------
@app.get("/eureka_search", response_model=Resp)
async def eureka_search_get(
    q: str = Query(...),
    limit: int = Query(5),
    token: str | None = Query(None),
    authorization: str = Header(default="")
):
    check_auth(authorization, token)
    return await do_search(q.strip(), limit)

@app.post("/eureka_search", response_model=Resp)
async def eureka_search_post(
    req: SearchReq,
    token: str | None = Query(None),
    authorization: str = Header(default="")
):
    check_auth(authorization, token)
    return await do_search(req.q.strip(), req.limit)
