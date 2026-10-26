# PlayPod

Self-hosted podcast player with a web interface, optional MPD playback and a separate browser player. Python/FastAPI, SQLite and Lit/TypeScript. Version **1.0.0**.

[Deutsch](docs/README.de.md) · [Node-RED and API](NODE-RED.md) · [Publishing releases](docs/RELEASING.md)

## Features

- Compact Library: podcast navigation, episode action menus and visible download progress. Remove local copies per episode or all finished downloads of a podcast; storage/orphan cleanup lives in Settings.

- RSS subscriptions, episode search, bookmarks, playback progress and editable queues.
- Activity timeline for new episodes and finished listening (MPD/browser), with exact episode links and a per-browser unseen counter. Events are kept for 90 days; initial feed imports are summarized.
- Normal playback stops when the queue is empty. Optional sleep mode uses a configurable timer and random continuation: all episodes or only episodes not fully played.
- Browser playback with its own queue/timer. MPD is optional and remains the default when configured.
- Integrated RSS downloads, yt-dlp audio imports and read-only external media folders. Completed downloads are preferred on the next playback start.
- German and English interface: automatic browser-language detection and a saved selection in Settings. Dates and numbers follow the chosen language. Feed titles, descriptions and third-party diagnostics retain their original language.
- Installable PWA with shortcuts and an offline notice. Audio and the library require the server; offline audio is not included.
- REST API, optional MQTT status and title announcements through a Node-RED/Home Assistant audio-URL endpoint.
- Fire-and-forget text announcements via `POST /api/v1/announcements`: persistent FIFO queue, automatic TTS, suspended sleep timer and MPD resume after the complete batch.

## Start with Docker

Copy `.env.example` to `.env`, then run:

```sh
docker compose up -d --build
```

Open `http://HOST:9393`. Leave `MPD_HOST` empty for browser-only playback. Set it to an MPD host to enable central playback. Add subscriptions in Library. Authentication can be handled by your reverse proxy.

**Alpine is the default.** The runtime contains Python 3.12, FFmpeg, yt-dlp/EJS and QuickJS-NG. Node is only used in the frontend build stage. To build the Debian alternative:

```sh
docker compose -f compose.yml -f compose.debian.yml up -d --build
```

Use the same project directory/name to keep the existing `playpod-data` volume. No database reset or new volume is required when switching images. Keep a database backup before updating; schema upgrades make a consistent backup before migration. Do not run two installations against the same database or MPD simultaneously.

### Published images

The GitHub workflow publishes to `ghcr.io/<owner>/<repository>` using the repository's name. A stable `v1.0.0` GitHub Release produces:

Published Alpine tags: `1.0.0`, `1.0.0-alpine`, `1.0`, `1`, `latest` (amd64 and arm64). Debian remains available as a local build only.

Set `PLAYPOD_IMAGE` in `.env` to the desired image, then use the published image without rebuilding:

```sh
docker compose pull playpod
docker compose up -d --no-build
```

Publishing the workflow files alone does not publish an image. See [release instructions](docs/RELEASING.md).

## Configuration

| Variable | Default / purpose |
| --- | --- |
| `PLAYPOD_IMAGE` | `playpod:local`; image tag for Compose builds or pulls |
| `MPD_HOST`, `MPD_PORT`, `MPD_PASSWORD` | Empty host disables MPD; port `6600`, optional password |
| `SQLITE_PATH` | `/data/playpod.sqlite3` in Docker |
| `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD` | Optional MQTT; port `1883` |
| `MQTT_TOPIC` | `podplayer/status`; retained `play`, `pause`, `stop`, `error` |
| `TTS_AUDIO_URL` | Optional endpoint returning an audio URL for playback through MPD; see [Node-RED](NODE-RED.md) |
| `TTS_TIMEOUT_SECONDS` | `10`; timeout while requesting announcement audio |
| `TTS_PLAYBACK_TIMEOUT_SECONDS` | `120`; maximum active announcement time |
| `RSS_INTERVAL_SECONDS` | `3600`, minimum `60` |
| `MEDIA_BASE_URL` | PlayPod URL reachable by MPD for local media/downloads; browser playback does not need it |
| `MEDIA_ROOTS` | JSON object mapping names to absolute container paths; empty by default |
| `MEDIA_STABLE_SECONDS` | `5`; minimum file stability before import |
| `DOWNLOAD_DIRECTORY` | `/data/downloads` in Docker |
| `DOWNLOAD_MAX_BYTES` | `2147483648` per file |
| `YTDLP_ENABLED` | `true`; disable page-link imports while keeping direct RSS downloads |
| `YTDLP_JS_RUNTIME` | `quickjs`; Docker includes `qjs`. Native installations can explicitly select `node` instead |
| `YTDLP_TIMEOUT` | `3600`; timeout for an entire page-link download |
| `ACCESS_LOG` | `false`; HTTP access logging. Application warnings/errors remain enabled |
| `TZ` | `Europe/Berlin` in Compose |

Sleep duration (initially 15 minutes) and random selection are configured in the UI. Playback status and the browser destination switch live inside the Player card. The random switch beside the timer allows Play to choose an episode even with no current selection. Changing defaults does not alter a current run. UI Pause/Resume retains remaining time and extensions; Next preserves the remaining time and extensions; an explicit episode start restarts the selected duration. Ending sleep mode pauses playback and disables its timer/random continuation. After a timer has fully expired, Play starts a new period.

Random selection always starts episodes at 0:00. “Not fully played” includes partially played episodes and excludes completed episodes; an empty pool stops playback. Explicit episode and queue selections resume saved progress. The queue always takes priority over random selection.

### Local folders

Mount external media read-only. For example:

```yaml
services:
  playpod:
    environment:
      MEDIA_ROOTS: '{"podcasts":"/media/podcasts","imports":"/media/imports"}'
    volumes:
      - /srv/podcasts:/media/podcasts:ro
      - /srv/imports:/media/imports:ro
```

Scan them from Settings. Removing a local library entry does not delete its file. `compose.media.yml` provides a single-folder example using `MEDIA_DIRECTORY`. Its mount target must also be included in `MEDIA_ROOTS`.

Downloads run inside the same container. yt-dlp imports single video/audio links and metadata-only YouTube playlist/channel subscriptions. Shorts and livestreams are excluded. Deleting a downloaded copy preserves the episode, bookmarks and progress. Orphan cleanup affects only managed download files. Files still referenced by MPD are protected. Third-party site availability depends on yt-dlp and the source site.

## Playback targets and PWA

With MPD configured, the “Play in this browser” switch selects a device-local player. Switching to the browser leaves MPD running independently; switching back pauses browser audio. Selecting a target never starts playback. Reload restores browser selection and queue without autoplay. Episode progress/bookmarks are shared, so simultaneous playback of the same episode uses the latest stored progress.

Install the PWA through the browser menu on HTTPS or localhost. MPD continues on the server; browser playback/timer execution depends on the browser and operating system remaining active. Background execution on mobile is not guaranteed. PWA updates do not force reload or interrupt audio. Authentication redirects, API responses and audio are not cached.

Keyboard: Space Play/Pause, Left/Right seek 30 seconds, Up/Down volume, N next, P player. Shortcuts do not run while typing or inside a dialog.

## API and health

Interactive schema: `/docs`; OpenAPI: `/openapi.json`. Node-RED controls the central MPD player; browser queues remain local. Without MPD, central playback commands return `mpd_not_configured`.

- `/api/live`: process liveness, used by the Docker healthcheck.
- `/api/health`: SQLite and optional MPD checks.
- `/api/v1/state`: cached player state; it does not issue an MPD request for every browser poll. Persistent MPD command and `idle` connections keep the state updated.

See [NODE-RED.md](NODE-RED.md) and the importable [example flow](examples/node-red-playpod-v1.json).

## Development and tests

UI translations live in `frontend/src/messages.ts`; wrap interface messages with `t()` from `i18n.ts` and preserve named placeholders. The coverage test checks that every translated call has an English entry. Content and third-party diagnostics are not translated.

Requirements: Python 3.12, Node 24 for frontend development, FFmpeg/ffprobe and QuickJS-NG (`qjs`) for downloads/tests. Install `requirements-dev.txt`, run `npm ci` in `frontend`, then:

```sh
npm --prefix frontend test
npm --prefix frontend run build
python -m pytest -q
python -m app
```

For live UI development run `npm run dev` in `frontend`; requests are proxied to the backend on port 9393. Native installation with Node instead of QuickJS requires `YTDLP_JS_RUNTIME=node`. `python -m app --version` reports the release version.

`sh scripts/compare-images.sh [OLD_IMAGE_TAG]` builds and checks Alpine/Debian separately without using the production volume, then writes local uncompressed image sizes to `build/image-sizes.tsv`. `scripts/smoke_image.py` checks runtime/EJS, API, SQLite, frontend and a real local yt-dlp/FFmpeg download; `--youtube-url URL` optionally checks public YouTube metadata/formats. Full container execution and GHCR publication run in GitHub Actions.


### Automatic RSS updates

`RSS_INTERVAL_SECONDS` is measured in seconds (43200 = 720 minutes = 12 hours). PlayPod persists the last full refresh start. Restarting preserves the deadline and immediately catches up an overdue run. On upgrade it uses the oldest existing RSS feed attempt; feeds never checked are immediately due. A manual full refresh resets the deadline; refreshing one podcast does not. Running refresh jobs are allowed to finish, with the scheduler checking again within a minute. Temporary scheduling failures are logged and retried after a minute. Individual feed errors are retried at the regular interval. Settings → Technical details and connections shows the latest job, the next automatic update and an inactive-scheduler warning when applicable.

Interrupted full refresh jobs are retried after restart instead of waiting another interval.


### YouTube collections

Use Library → Import link and select a single video, YouTube playlist or channel. Single links download immediately into **YouTube · Einzelimporte**. Subscriptions appear separately with their source type and thumbnails, and use `RSS_INTERVAL_SECONDS` for periodic checks. Choose an initial count (default 50) or all: channels use latest videos, playlists their source order. Subsequent checks add new IDs without downloading audio, and do not silently import the older entries excluded by the initial count. Private/deleted entries are not newly imported. Only complete catalog responses can remove missing entries; existing local copies are retained until explicitly deleted.

Adding a YouTube episode to the queue or marking it for later starts an idempotent audio download. RSS episodes continue to stream. Random only uses ready YouTube downloads and excludes hidden entries. A queue transition waits for a pending download with the sleep timer frozen; failures are marked in the queue and skipped. Pause cancels the pending autoplay intent, not the download. Removing a queue entry or bookmark does not cancel downloading. Browser and MPD queues retain their separate operation.

Individual imports can be removed with their files, or just their local copy can be deleted. Playlist/channel items can be hidden/unhidden, rather than manually deleted. Deleting a YouTube collection removes all its entries and managed audio files after confirmation; duplicate copies in other collections are independent. In-use browser downloads must first be released. External media directories are never deleted. Thumbnails are remote image URLs; playback still uses downloaded audio.

Database schema 6 adds import limits and hidden flags; upgrading an existing database creates a `.before-v6.sqlite3` backup. Older application versions cannot open schema 6.
