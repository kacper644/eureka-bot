import hashlib
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

from playwright.async_api import async_playwright

app = FastAPI()

API_TOKEN = ""  # nadamy w Railway przez zmienną środowiskową

class SearchReq(BaseModel):
    q: str = Field(..., description="fraza, np. 'fundacja rodzinna'")
    limit: int = Field(10, ge=1, le=50)

class Item(BaseModel):
    title: str
    url: str
    date: Optional[str] = None
    snippet: Optional[str] = None
    id: str

class SearchResp(BaseModel):
    count: int
    results: List[Item]

async def _scrape_eureka(query: str, limit: int) -> List[dict]:
    # Otwieramy Eurekę w przeglądarce bezgłowej, wpisujemy frazę, bierzemy linki do interpretacji
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        # 1) Strona główna
        await page.goto("https://eureka.mf.gov.pl/", wait_until="domcontentloaded")

        # 2) Pole wyszukiwania: spróbujemy po placeholderze/aria-labelu i po tekście przycisku
        # (Selektory są ogólne, ale stabilne: jeśli UI się zmieni, dostosujemy)
        # Spróbuj znaleźć input:
        input_locator = page.locator('input[placeholder*="fra"] , input[aria-label*="szuk"], input[type="search"]')
        await input_locator.first().fill(query)

        # Przyciski "Szukaj":
        search_btn = page.locator('button:has-text("Szukaj"), input[type="submit"]')
        await search_btn.first().click()

        # 3) Poczekaj aż pojawią się wyniki z linkami do podglądu interpretacji
        await page.wait_for_load_state("networkidle")
        await page.wait_for_selector('a[href*="/informacje/podglad/"]', timeout=15000)

        links = page.locator('a[href*="/informacje/podglad/"]')
        count = await links.count()
        out = []
        for i in range(min(count, limit*2)):  # bierzemy trochę więcej, odfiltrujemy duplikaty
            href = await links.nth(i).get_attribute("href")
            title = (await links.nth(i).inner_text()).strip()
            if not href or not title:
                continue
            url = page.url.split("/szukaj")[0] + href if href.startswith("/") else href

            # Kontekst (data + krótki opis) z najbliższego kontenera
            block = links.nth(i).locator("xpath=ancestor-or-self::*[self::a or self::div or self::li][1]")
            ctx_text = ""
            try:
                ctx_text = (await block.inner_text()).strip()
            except:
                pass

            # Proste wyłuskanie daty (YYYY-MM-DD albo DD.MM.RRRR)
            date = None
            import re
            m = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", ctx_text)
            if m:
                raw = m.group(1)
                # normalizacja do YYYY-MM-DD
                try:
                    from dateutil import parser as dparser
                    dt = dparser.parse(raw, dayfirst=True, fuzzy=True)
                    date = dt.date().isoformat()
                except:
                    date = None

            snippet = " ".join(ctx_text.split())[:240] if ctx_text else None
            _id = hashlib.md5((url + (date or "")).encode("utf-8")).hexdigest()

            item = {"title": title, "url": url, "date": date, "snippet": snippet, "id": _id}
            # unikaj duplikatów po URL
            if not any(x["url"] == url for x in out):
                out.append(item)

            if len(out) >= limit:
                break

        await context.close()
        await browser.close()
        return out

@app.post("/eureka_search", response_model=SearchResp)
async def eureka_search(req: SearchReq, authorization: str = Header(default="")):
    global API_TOKEN
    # prosta autoryzacja przez nagłówek
    if API_TOKEN and authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(401, "unauthorized")

    results = await _scrape_eureka(req.q, req.limit)
    return {"count": len(results), "results": results}
