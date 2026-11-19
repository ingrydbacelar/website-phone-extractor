# Extrator de Telefones

Duas partes:

- `index.html`, `style.css` e `script.js` — a página da ferramenta (ficam no GitHub Pages, com a mesma identidade visual do Validador de E-mails).
- `backend/` — a API em Python que visita os sites e extrai os telefones. O GitHub Pages só serve arquivos estáticos e não roda Python, por isso a API precisa de outro lugar.

## 1. Publicar a API (ex.: Render)

1. Suba a pasta `backend/` para um repositório no GitHub (pode ser o mesmo da página, em uma subpasta).
2. No Render: **New > Web Service**, aponte para o repositório, em *Root Directory* coloque `backend` e escolha **Docker**.
3. Variáveis de ambiente:
   - `ALLOWED_ORIGINS` = `https://SEUUSUARIO.github.io` (sem barra no final). Só esse endereço poderá usar a API pela página.
   - `API_TOKEN` = uma chave qualquer (opcional, mas recomendado, para ninguém usar sua API). Digite a mesma chave em *Configurações* na página.
4. Copie o endereço gerado (ex.: `https://extrator-xxxx.onrender.com`).

No plano gratuito do Render a API "dorme" e a primeira consulta pode levar cerca de 1 minuto.

### Playwright (opcional)

Para sites que só mostram o telefone depois de rodar JavaScript, troque `ARG PLAYWRIGHT=0` por `ARG PLAYWRIGHT=1` no `Dockerfile`. Precisa de uma instância com pelo menos 1–2 GB de RAM. Sem ele, o resto da lógica funciona normalmente.

## 2. Publicar a página

1. Abra `script.js` e troque `API_URL` pelo endereço da API.
2. Coloque os três arquivos (`index.html`, `style.css`, `script.js`) na mesma pasta do repositório do GitHub Pages (ex.: `/extrator-telefones/`).

## Testar localmente

```
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Depois defina `API_URL = "http://localhost:8000"` no `script.js` e abra o arquivo no navegador.

## O que mudou na lógica

- Visita a página inicial e as páginas de contato (achadas pelos links ou por `/contato` e `/fale-conosco`).
- Lê links `tel:`, links de WhatsApp, dados estruturados (JSON-LD) e o texto visível.
- Normaliza espaços antes da regex e valida DDD, para aceitar `(98) <span>3222-1234</span>` e `+55 (98) 9 9999-9999` e descartar CEP, CNPJ e datas.
- Usa o Playwright como última tentativa, sem depender do tamanho do HTML.
- Mostra todos os números encontrados, a origem de cada um e o motivo quando falha.
- Sites fora do ar (domínio que não existe, servidor que não conecta em 6 s, erro 5xx) são marcados como **Site fora do ar** na hora, sem tentar outras páginas.
- Sites lentos são marcados como **Site lento**: se a página inicial não responde a tempo, o site é pulado; se responde devagar (mais de 8 s) ou o limite de 30 s por site estoura, o resultado sai com o aviso. Ao final, a página mostra um resumo com as contagens.
- Bloqueia endereços internos (localhost, IPs privados) para a API não ser usada para varrer rede interna.

Números sem DDD (ex.: só `3222-1234`) são ignorados de propósito, porque não dá para distinguir de outros códigos.
