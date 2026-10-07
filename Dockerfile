FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    U2NET_HOME=/models/u2net \
    NAME_REGISTRY_PATH=/runtime-data/generated_names.json

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /models/u2net /runtime-data

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY templates ./templates
COPY template.pdf ./template.pdf
COPY runtime-data/generated_names.json /runtime-data/generated_names.json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5m --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers"]