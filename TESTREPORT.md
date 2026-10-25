# PlayPod 1.0.0 validation

## Local checks

- Backend: 233 current tests covered by the full 232-test run and the subsequent targeted 13-test run including the new English-manifest test. All passed. One existing Starlette/httpx deprecation warning.
- Frontend: 42 tests passed, including browser playback, timers, keyboard, Node-RED example mappings, PWA cache rules and i18n detection/persistence/messages/placeholders/counts/offline/error handling. TypeScript and production build passed.
- Release versions agree at 1.0.0. Release-tag check v1.0.0 passes. Tests cover stable/prerelease/main tags and separate Debian aliases.
- GitHub workflow parsed and checked with actionlint 1.7.12 without errors. Compose YAML and shell-script syntax checked. Native amd64/arm64 image jobs and digest-based publication are configured; not executed on GitHub here.
- QuickJS/yt-dlp runtime smoke passed locally: bundled EJS loaded via the actual provider; API, SQLite, RSS parser, frontend, local yt-dlp child, FFmpeg MP3 conversion and HTTP range streaming succeeded.
- Browser checks used an isolated test API: English/German live switch, persistence after reload, translated navigation/dialogs/known feed errors, locale date formatting, 44px-aligned sleep inputs, English settings save/reload and matching manifest language.
- Mobile layout checked in 390px and 320px frames: no horizontal overflow, readable language picker and retained player/sleep layout. English screenshot created for the handoff.
- Alpine is the default based on the user's successful prior test. Debian remains an explicit alternative. Existing SQLite migrations, persistent data and central API playback behavior are preserved. Deprecated embedded configuration was removed from code/configuration/docs.

## Target-environment checks

No Docker engine, GHCR publication or GitHub release was executed in this environment. The workflow performs native image builds and offline runtime checks when run in the repository. Real MPD/Home Assistant/MQTT output, HTTPS/PWA installation and mobile background behavior remain target-environment checks. The browser UI check does not claim real loudspeaker output. No database reset is introduced.
