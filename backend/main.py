import hmac
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from extrator import extrair_telefones

app = FastAPI(title="Extrator de Telefones")

# Ex.: ALLOWED_ORIGINS=https://seuusuario.github.io  (sem barra no final, sem caminho)
origens = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origens,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Opcional: se definido, a página precisa enviar a mesma chave no cabeçalho X-Token.
TOKEN = os.getenv("API_TOKEN", "")


class Pedido(BaseModel):
    url: str


@app.get("/")
def status():
    return {"ok": True}


@app.post("/extrair")
async def extrair(pedido: Pedido, x_token: str = Header(default="")):
    if TOKEN and not hmac.compare_digest(x_token, TOKEN):
        raise HTTPException(status_code=401, detail="Chave inválida")
    return await run_in_threadpool(extrair_telefones, pedido.url.strip()[:500])
