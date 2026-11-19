FROM python:3.12-slim

# Mude para 1 se quiser o Playwright (sites que montam o telefone com JavaScript).
# Exige instância com pelo menos 1–2 GB de RAM.
ARG PLAYWRIGHT=0

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN if [ "$PLAYWRIGHT" = "1" ]; then \
      pip install --no-cache-dir playwright && playwright install --with-deps chromium; \
    fi
COPY . .
ENV USE_PLAYWRIGHT=$PLAYWRIGHT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
