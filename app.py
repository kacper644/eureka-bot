import hashlib
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from typing import List
from playwright.async_api import async_playwright
import os

app = FastAPI()

class SearchReq(BaseModel):
    q: str = Field(..., description="fraza, np. 'fundacja rodzinna'")
    limit: int = Field(5, ge=1, le=20)

class Item(BaseModel):
    title: str
    url: str

class Resp(BaseModel):
    count: int
    results: List[Item]

@app.get("/ping")
async def ping():
    return {"ok": True}

@app.post("/eureka_search", response_model=Resp)
async def eureka_search(req: SearchReq, authorization: str = Header(default="")):
    token = os.getenv("API_TOKEN", "")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "unauthorized")

    q = req.q.strip()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(locale="pl-PL")
        page = await context.new_page()

        # Wejście na Eurekę
        await page.goto("https://eureka.mf.gov.pl/", wait_until="domcontentloaded")

        # Wpisanie frazy
        selectors = [
            'input[type="search"]',
            'input[placeholder*="fra"]',
            'input[aria-label*="szuk"]'
        ]
        for sel in selectors:
            if await page.locator(sel).first().count():
                await page.locator(sel).first().fill(q)
                break
        else:
            raise HTTPException(502, "search box not found")

        # Klik „Szukaj”
        btn = page.locator('button:has-text("Szukaj"), input[type="submit"]')
        await btn.first().click()

        # Czekamy na linki wyników (podgląd interpretacji)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_selector('a[href*="/informacje/podglad/"]', timeout=20000)
        links = page.locator('a[href*="/informacje/podglad/"]')
        n = await links.count()

        out = []
        for i in range(min(n, req.limit)):
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
