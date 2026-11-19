"""Extração de telefones (Brasil) a partir do site de uma empresa."""
import ipaddress
import os
import random
import re
import socket
import threading
import time
from urllib.parse import unquote, urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# Ligue com USE_PLAYWRIGHT=1 (precisa do Playwright + Chromium instalados).
USE_PLAYWRIGHT = os.getenv("USE_PLAYWRIGHT", "0") == "1"
_PLAYWRIGHT_LOCK = threading.Semaphore(1)  # um navegador por vez (economiza RAM)

DDDS = set(
    "11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 "
    "41 42 43 44 45 46 47 48 49 51 53 54 55 61 62 63 64 65 66 67 68 69 "
    "71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 91 92 93 94 95 96 97 98 99".split()
)

# (+55) (DDD) [9] XXXX-XXXX, tolerando espaços, pontos e hífens em qualquer posição.
RE_TEL = re.compile(
    r"(?<!\d)(?:\+?\s*55[\s.\-]*)?\(?\s*0?(\d{2})\s*\)?[\s.\-]*(9?)[\s.\-]*(\d{4})[\s.\-]*(\d{4})(?!\d)"
)
RE_0800 = re.compile(r"(?<!\d)0?800[\s.\-]*\d{3}[\s.\-]*\d{4}(?!\d)")
RE_CONTATO = re.compile(r"contat|fale|atendimento|sobre|quem[\s\-_]?somos|onde|unidade|localiza", re.I)

FORA = "Site fora do ar"
LENTO = "Site lento"
LIMITE_SITE = 30   # segundos no máximo por site (soma de todas as páginas visitadas)
LIMITE_LENTO = 8   # página inicial que leva mais que isso é marcada como lenta

PESOS = {"tel": 100, "jsonld": 80, "whatsapp": 60, "texto": 40}
ROTULOS = {
    "tel": "link de telefone",
    "jsonld": "dados estruturados",
    "whatsapp": "link de WhatsApp",
    "texto": "texto da página",
}


# ---------------------------------------------------------------- números

def normalizar(bruto):
    """Devolve só os dígitos (DDD + número) se for um telefone BR válido; senão None."""
    d = re.sub(r"\D", "", bruto or "")
    if d.startswith("0800") and len(d) == 11:
        return d
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if d.startswith("0") and len(d) in (11, 12):
        d = d[1:]
    if len(d) == 11 and d[:2] in DDDS and d[2] == "9":
        return d
    if len(d) == 10 and d[:2] in DDDS and d[2] in "2345":
        return d
    return None


def formatar(d):
    if d.startswith("0800"):
        return f"0800 {d[4:7]} {d[7:]}"
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    return f"({d[:2]}) {d[2:6]}-{d[6:]}"


# ---------------------------------------------------------------- rede

def verificar_host(host):
    """None se estiver ok; senão a mensagem de erro."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return FORA  # domínio não existe / DNS não resolve
    if not all(ipaddress.ip_address(i[4][0]).is_global for i in infos):
        return "Endereço não permitido"  # evita varrer localhost/rede interna
    return None


def buscar(url, sessao, max_redirects=5):
    """Retorna (conteudo, url_final, erro). Erros: FORA, LENTO, "CONEXAO" (interno), outros."""
    inicio = time.monotonic()
    for _ in range(max_redirects + 1):
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return None, url, "URL inválida"
        erro_host = verificar_host(p.hostname)
        if erro_host:
            return None, url, erro_host
        try:
            r = sessao.get(url, timeout=(6, 10), verify=False, allow_redirects=False, stream=True)
        except requests.exceptions.ConnectTimeout:
            return None, url, FORA      # nem conectou em 6 s
        except requests.exceptions.Timeout:
            return None, url, LENTO     # conectou, mas não respondeu a tempo
        except requests.exceptions.ConnectionError:
            return None, url, "CONEXAO"
        except Exception as e:
            return None, url, f"Erro: {type(e).__name__}"

        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            url = urljoin(url, r.headers["Location"])
            r.close()
            continue
        if r.status_code in (500, 502, 504) or 520 <= r.status_code <= 526:
            r.close()
            return None, url, FORA
        if r.status_code in (403, 429, 503):
            r.close()
            return None, url, f"Bloqueado pelo site (HTTP {r.status_code})"
        if r.status_code != 200:
            r.close()
            return None, url, f"HTTP {r.status_code}"

        partes, total = [], 0
        try:
            for c in r.iter_content(65536):
                partes.append(c)
                total += len(c)
                if total > 3_000_000:
                    break
                if time.monotonic() - inicio > 15:
                    r.close()
                    return None, url, LENTO
        except (requests.exceptions.RequestException, OSError):
            r.close()
            return None, url, LENTO
        r.close()
        return b"".join(partes), url, None
    return None, url, "Redirecionamentos demais"


def renderizar(url):
    """Abre a página num navegador de verdade (para sites que montam o conteúdo com JS)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    with _PLAYWRIGHT_LOCK:
        try:
            with sync_playwright() as p:
                navegador = p.chromium.launch(headless=True, args=["--no-sandbox"])
                ctx = navegador.new_context(user_agent=UA, locale="pt-BR", ignore_https_errors=True)
                pagina = ctx.new_page()
                pagina.goto(url, wait_until="domcontentloaded", timeout=20000)
                try:
                    pagina.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass  # sites com chat/pixels nunca ficam "idle"; segue mesmo assim
                pagina.wait_for_timeout(1500)
                html = pagina.content()
                navegador.close()
                return html
        except Exception:
            return None


# ---------------------------------------------------------------- extração

def coletar(html, achados):
    """Lê telefones de links, dados estruturados e texto. Devolve o soup (sem scripts)."""
    soup = BeautifulSoup(html, "html.parser")

    def add(bruto, fonte):
        n = normalizar(bruto)
        if n:
            achados.setdefault(n, set()).add(fonte)

    # 1) links tel: e WhatsApp
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if low.startswith("tel:"):
            add(unquote(href[4:]), "tel")
        elif "wa.me/" in low or "whatsapp" in low:
            m = re.search(r"wa\.me/\+?(\d+)", low) or re.search(r"phone=\+?(\d+)", low)
            if m:
                add(m.group(1), "whatsapp")

    # 2) dados estruturados (JSON-LD e microdados) — ficam dentro de <script>
    for tag in soup.find_all(attrs={"itemprop": "telephone"}):
        add(tag.get("content") or tag.get_text(" "), "jsonld")
    for s in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        for m in re.finditer(r'"telephone"\s*:\s*\[?\s*"([^"]+)"', s.string or s.get_text()):
            add(m.group(1), "jsonld")

    # 3) texto visível (espaços normalizados antes da regex)
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    texto = re.sub(r"\s+", " ", soup.get_text(" "))
    for m in RE_TEL.finditer(texto):
        add(m.group(0), "texto")
    for m in RE_0800.finditer(texto):
        add(m.group(0), "texto")

    return soup


def links_contato(soup, base_url, limite=3):
    host = urlparse(base_url).netloc.replace("www.", "")
    achados = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urljoin(base_url, href).split("#")[0]
        p = urlparse(url)
        if p.scheme not in ("http", "https") or p.netloc.replace("www.", "") != host:
            continue
        if url.rstrip("/") == base_url.rstrip("/"):
            continue
        alvo = f"{p.path} {a.get_text(' ')}".lower()
        if RE_CONTATO.search(alvo):
            prioridade = 0 if re.search(r"contat|fale", alvo) else 1
            achados.setdefault(url, prioridade)
    return [u for u, _ in sorted(achados.items(), key=lambda x: x[1])][:limite]


def ranquear(achados):
    itens = []
    for ordem, (n, fontes) in enumerate(achados.items()):
        score = sum(PESOS[f] for f in fontes)
        if n.startswith("0800"):
            score -= 50  # geralmente é SAC, não o contato comercial
        elif len(n) == 11:
            score += 10  # celular/WhatsApp ganha de fixo em caso de empate
        itens.append((-score, ordem, n, fontes))
    itens.sort(key=lambda x: (x[0], x[1]))
    return [
        {
            "numero": formatar(n),
            "digitos": n,
            "fontes": [ROTULOS[f] for f in sorted(fontes, key=lambda x: -PESOS[x])],
        }
        for _, _, n, fontes in itens
    ]


def normalizar_url(u):
    u = (u or "").strip()
    if not u:
        return None
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urlparse(u)
    return u if p.hostname and "." in p.hostname else None


def pausa():
    time.sleep(random.uniform(0.3, 0.8))


def extrair_telefones(entrada):
    inicio = time.monotonic()
    prazo = inicio + LIMITE_SITE
    url = normalizar_url(entrada)
    if not url:
        return _resposta(entrada, [], 0, "URL inválida", "erro", inicio)

    sessao = requests.Session()
    sessao.headers.update(HEADERS)
    achados = {}
    paginas = 0

    # --- 1. página inicial
    t0 = time.monotonic()
    corpo, final, erro_home = buscar(url, sessao)
    if erro_home == "CONEXAO" and url.startswith("https://"):
        corpo, final, erro_home = buscar("http://" + url[8:], sessao)
    if erro_home == "CONEXAO":
        erro_home = FORA

    # Site fora do ar ou sem resposta: ignora, sem tentar outras páginas.
    if erro_home == FORA:
        return _resposta(entrada, [], 0, FORA, "fora_do_ar", inicio)
    if erro_home == LENTO:
        return _resposta(entrada, [], 0, "Site lento: sem resposta no tempo limite", "lento", inicio)

    lento = corpo is not None and (time.monotonic() - t0) > LIMITE_LENTO
    estourou = False

    links = []
    if corpo is not None:
        paginas += 1
        soup = coletar(corpo, achados)
        links = links_contato(soup, final)

    # --- 2. páginas de contato encontradas nos links
    visitadas = {final.rstrip("/")}
    if not achados:
        for l in links:
            if time.monotonic() > prazo:
                estourou = True
                break
            pausa()
            c, _, _ = buscar(l, sessao)
            visitadas.add(l.rstrip("/"))
            if c is not None:
                paginas += 1
                coletar(c, achados)
                if achados:
                    break

    # --- 3. caminhos comuns, se o site não linka a página de contato
    if not achados and corpo is not None and not estourou:
        p = urlparse(final)
        for caminho in ("/contato", "/fale-conosco"):
            alvo = f"{p.scheme}://{p.netloc}{caminho}"
            if alvo in visitadas:
                continue
            if time.monotonic() > prazo:
                estourou = True
                break
            pausa()
            c, _, _ = buscar(alvo, sessao)
            if c is not None:
                paginas += 1
                coletar(c, achados)
                if achados:
                    break

    # --- 4. navegador de verdade, se ainda não achou nada (e o site não está lento)
    renderizado = False
    pode_renderizar = erro_home is None or erro_home.startswith("Bloqueado")
    if not achados and USE_PLAYWRIGHT and pode_renderizar and not (lento or estourou):
        for alvo in [final] + links[:1]:
            html = renderizar(alvo)
            if html:
                renderizado = True
                paginas += 1
                coletar(html, achados)
                if achados:
                    break

    if achados:
        status = "lento" if (lento or estourou) else "ok"
        return _resposta(entrada, ranquear(achados), paginas, None, status, inicio, renderizado)
    if erro_home:
        status = "bloqueado" if erro_home.startswith("Bloqueado") else "erro"
        return _resposta(entrada, [], paginas, erro_home, status, inicio, renderizado)
    if lento or estourou:
        return _resposta(entrada, [], paginas, "Site lento: tempo limite atingido sem achar telefone",
                         "lento", inicio, renderizado)
    return _resposta(entrada, [], paginas, "Nenhum telefone encontrado", "sem_telefone", inicio, renderizado)


def _resposta(entrada, todos, paginas, erro, status, inicio, renderizado=False):
    return {
        "url": entrada,
        "status": status,  # ok | lento | fora_do_ar | bloqueado | sem_telefone | erro
        "telefone": todos[0]["numero"] if todos else None,
        "digitos": todos[0]["digitos"] if todos else None,
        "todos": todos,
        "paginas": paginas,
        "tempo": round(time.monotonic() - inicio, 1),
        "renderizado": renderizado,
        "erro": erro,
    }
