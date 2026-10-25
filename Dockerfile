# syntax=docker/dockerfile:1
FROM node:24-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM alpine:3.23 AS javascript
RUN apk add --no-cache build-base cmake curl ca-certificates
COPY docker/build-quickjs.sh /build-quickjs.sh
RUN sh /build-quickjs.sh /work /out

FROM python:3.12-alpine3.23 AS wheels
# Native wheels are preferred. Build dependencies stay in this stage when a
# dependency only provides source distributions for the target architecture.
RUN apk add --no-cache build-base cargo libffi-dev openssl-dev
WORKDIR /build
COPY requirements.lock ./
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.lock

FROM python:3.12-alpine3.23
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SQLITE_PATH=/data/playpod.sqlite3 STATIC_DIR=/app/frontend/dist YTDLP_JS_RUNTIME=quickjs
WORKDIR /app
COPY --from=javascript /out/qjs /usr/local/bin/qjs
COPY --from=javascript /out/LICENSE.quickjs-ng /usr/local/share/licenses/quickjs-ng/LICENSE
RUN apk add --no-cache ffmpeg ca-certificates libstdc++ libffi tzdata
COPY requirements.lock ./
# BuildKit mounts avoid storing the wheel archive in a runtime image layer.
RUN --mount=type=bind,from=wheels,source=/wheels,target=/wheels \
    pip install --no-index --no-cache-dir --no-compile --find-links=/wheels -r requirements.lock && \
    addgroup -g 10001 -S playpod && adduser -u 10001 -S -D -H -G playpod playpod && \
    mkdir /data && chown playpod:playpod /data
COPY --chown=playpod:playpod app ./app
COPY --from=frontend --chown=playpod:playpod /build/dist ./frontend/dist
USER playpod
EXPOSE 9393
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9393/api/live',timeout=3)"
CMD ["python", "-m", "app"]
