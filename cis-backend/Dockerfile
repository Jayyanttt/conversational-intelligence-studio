# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.11-slim
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite:////data/app.db
RUN useradd --system --uid 10001 --no-create-home appuser && mkdir /data && chown appuser /data
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY app ./app
USER appuser
EXPOSE 8000
VOLUME /data
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"
# One worker because LiteLLM cache is in-memory and process-local.
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
