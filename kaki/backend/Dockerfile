# ── Kaki Backend — built for IBM LinuxONE (s390x), works on amd64/arm64 too ──
# Build context is the PROJECT ROOT (it needs train.py, kaki_ml.py, models/):
#   docker buildx build --platform linux/s390x -f backend/Dockerfile -t kaki-backend .
# If models/manifest.json exists in the context, those pre-trained models are
# used; otherwise the train stage runs train.py (downloads from Kaggle).

# ---------- train stage ----------
FROM python:3.11-slim AS train
WORKDIR /src
# Compilers/BLAS in case pip has no prebuilt wheel for this architecture (s390x)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gfortran libopenblas-dev pkg-config \
 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements.txt
COPY requirements-train.txt .
RUN pip install --no-cache-dir -r requirements-train.txt
COPY . .
RUN if [ -f models/manifest.json ]; then echo "Using pre-trained models from build context"; \
    else python train.py --no-plots; fi

# ---------- runtime stage ----------
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libopenblas0 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=train /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=train /usr/local/bin/gunicorn /usr/local/bin/gunicorn
COPY kaki_ml.py backend/app.py ./
COPY --from=train /src/models ./models
# Model files stay root-owned and read-only; the server runs unprivileged.
RUN chmod -R a-w ./models && useradd --system --no-create-home kaki
USER kaki

EXPOSE 5001
ENV PORT=5001 KAKI_MODEL_DIR=/app/models
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5001/api/health', timeout=4).status == 200 else 1)"
# --preload loads the models once, before workers fork.
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "--timeout", "60", "--preload", "app:create_app()"]
