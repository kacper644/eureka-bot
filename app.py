from fastapi import FastAPI, HTTPException, Header, Query
from pydantic import BaseModel
from typing import List
import os

app = FastAPI()

# MODELE
class Item(BaseModel):
    title: str
    url: str

class Resp(BaseModel):
    count: int
    results: List[Item]

# PROSTA AUTORYZACJA (nagłówek Bearer ALBO query ?token=)
def check_auth(authorization: str, token_q: str | None):
    token_env = os.getenv("API_TOKEN", "")
    if not token_env:
        return
    if authorization == f"Bearer {token_env}":
        return
    if token_q == token_env:
        return
    raise HTTPException(401, "unauthorized")

# ROUTES
@app.get("/ping")
def ping():
    return {"ok": True}

@app.get("/eureka_search", response_model=Resp)
def eureka_search_get(
    q: str = Query(...),
    limit: int = Query(5, ge=1, le=20),
    token: str | None = Query(None),
    authorization: str = Header(default="")
):
    check_auth(authorization, token)
    # TU JESZCZE NIE SCRAPUJEMY — zwracamy PRZYKŁADOWE dane,
    # żeby sprawdzić n8n→Telegram.
    examples = [
        {"title": "Fundacja rodzinna – przykład 1", "url": "https://eureka.mf.gov.pl/informacje/podglad/123"},
        {"title": "Fundacja rodzinna – przykład 2", "url": "https://eureka.mf.gov.pl/informacje/podglad/456"},
        {"title": "Fundacja rodzinna – przykład 3", "url": "https://eureka.mf.gov.pl/informacje/podglad/789"},
    ]
    return {"count": min(limit, len(examples)), "results": examples[:limit]}
