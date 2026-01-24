# =========================================================================
# Estágio 1: O "Construtor" (Builder) - (Sem alterações aqui)
# =========================================================================
FROM python:3.13-slim AS builder

ENV PLAYWRIGHT_BROWSERS_PATH=/app/pw-browsers
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install-deps firefox
RUN playwright install firefox


# =========================================================================
# Estágio 2: A Imagem Final (Final Stage) - (A correção está aqui)
# =========================================================================
FROM python:3.13-slim

ENV PLAYWRIGHT_BROWSERS_PATH=/app/pw-browsers
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Instala dependências de sistema/browsers do Playwright e os browsers
RUN playwright install-deps firefox && playwright install firefox

# Copia browsers gerados no estágio de build (economiza tempo em rebuilds)
COPY --from=builder /app/pw-browsers /app/pw-browsers

COPY dados/ ./dados/
COPY fluxos/ ./fluxos/
COPY utils/ ./utils/
COPY workers/ ./workers/
COPY main.py .
COPY poller.py .
COPY writer.py .

CMD ["python", "main.py"]