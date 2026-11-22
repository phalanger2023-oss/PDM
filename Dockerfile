# ---- Étape 1 : récupère PDF.js (la bibliothèque qui affiche les PDF) pour l'héberger avec le site ----
FROM node:22-alpine AS pdfjs
WORKDIR /w
RUN npm install --no-audit --no-fund pdfjs-dist@3.11.174

# ---- Étape 2 : le site (Python) ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    BEHIND_PROXY=1 \
    DOCS_DIR=/data/documents

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0

COPY app.py pdfedit.py releases.py ./
COPY static ./static
COPY --from=pdfjs /w/node_modules/pdfjs-dist/build/pdf.min.js /w/node_modules/pdfjs-dist/build/pdf.worker.min.js ./static/vendor/

# Le site tourne avec un utilisateur sans droits particuliers ; les documents vivent dans un volume
RUN useradd --system --uid 10001 appuser \
    && mkdir -p /data/documents \
    && chown -R appuser /data
USER appuser

EXPOSE 8000

# Traefik retire automatiquement du routage un conteneur « unhealthy »
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

# Plusieurs processus (et non des « threads ») : la bibliothèque PDF n'est pas faite pour les threads
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "app:app"]
