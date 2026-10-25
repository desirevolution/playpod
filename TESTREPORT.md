# PlayPod 1.0.0 validation

## Local checks

- Backend: 268 tests passed in a full run, followed by 57 targeted custom/mode announcement checks after adding favorite speech to the batch (269 current tests covered). Includes activity import summaries, insertion deduplication, completion retries/replays, retention, deletion snapshots, cursor pagination, unseen counts, exact episode locations and schema-5 migration/backup. One existing Starlette/httpx deprecation warning.
- Frontend: 45 tests passed, including browser playback, timers, keyboard, Node-RED example mappings, PWA cache rules and i18n detection/persistence/messages/placeholders/counts/offline/error handling. TypeScript and production build passed.
- Release versions agree at 1.0.0. Release-tag check v1.0.0 passes. Tests cover stable/prerelease/main tags and release tag generation. Only Alpine is published; Debian remains a local build option.
- GitHub workflow parsed and checked with actionlint 1.7.12 without errors. Compose YAML and shell-script syntax checked. Native amd64/arm64 image jobs and digest-based publication are configured; not executed on GitHub here.
- QuickJS/yt-dlp runtime smoke passed locally: bundled EJS loaded via the actual provider; API, SQLite, RSS parser, frontend, local yt-dlp child, FFmpeg MP3 conversion and HTTP range streaming succeeded.
- Browser checks used an isolated test API: English/German live switch, persistence after reload, translated navigation/dialogs/known feed errors, locale date formatting, 44px-aligned sleep inputs, English settings save/reload and matching manifest language.
- Mobile layout checked in 390px and 320px frames: no horizontal overflow, readable language picker and retained player/sleep layout. English screenshot created for the handoff.
- Alpine is the default based on the user's successful prior test. Debian remains an explicit alternative. Existing SQLite migrations, persistent data and central API playback behavior are preserved. Deprecated embedded configuration was removed from code/configuration/docs.

## Activity update

- Activity events persist transactionally with catalog/progress changes in SQLite schema 5; existing catalogs are not backfilled. A v5 backup is made before upgrading an existing database.
- RSS initial imports are summarized; later new rows create individual events. Local scans and yt-dlp imports also produce events without duplicating them on rescans/retries.
- The browser uses a persisted playback identifier so completion retries do not duplicate events. Existing progress clients remain supported.
- Browser UI checks with isolated fixtures: unseen counter (99+), marking seen and reload persistence, German/English texts, filter and 100-row pagination, exact episode focus/highlight on page 3.
- Activity at 320px and 390px: four navigation items fit; document width equals content width (305px and 375px excluding scrollbars). Desktop screenshot saved for the handoff.
- Desktop player uses the available width. The logo opens the GitHub repository in a new tab.

## Queued text announcements

- POST /api/v1/announcements durably acknowledges text with HTTP 202 before generating or playing speech. The worker starts with the application; callers need no polling or callback.
- Tests cover FIFO playback, no podcast restart between messages, whole-batch sleep-timer suspension, generation while playback continues, concurrent enqueue/control requests, the Node-RED UTF-8 TTS contract, play/pause/stop/idle restoration, queue/context restart recovery, failed first/middle/last messages, decode errors/timeouts, limits, validation and optional status endpoints.
- Favorite speech joins an existing custom batch; mode/title regressions pass. Manual episode changes cancel the current batch. Completion activity and episode queues stay unchanged.
- Queue and last 100 terminal results use existing SQLite settings; no schema change or extra container. State exposes announcement_kind=custom; the UI displays the text in German/English.
- MPD transitions use the simulated MPD adapter; real audio output remains a target-environment check.

## Target-environment checks

No Docker engine, GHCR publication or GitHub release was executed in this environment. The workflow performs native image builds and offline runtime checks when run in the repository. Real MPD/Home Assistant/MQTT output, HTTPS/PWA installation and mobile background behavior remain target-environment checks. The browser UI check does not claim real loudspeaker output. No database reset is introduced.

## Layout follow-up

- Removed the content width limit for every view. Desktop player columns use 3fr/2fr (60:40); the existing mobile single-column breakpoint remains.
- Playback status now belongs to the target group above the browser switch. Timer readouts render only during playback with an enabled timer, including the mini-player; the timer selector retains its Off option.
- All 45 frontend tests, TypeScript and the production build passed. No backend behavior changed in this follow-up.
