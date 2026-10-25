# Changelog

## Unreleased

- Fire-and-forget text announcement API with persistent FIFO processing, shared TTS integration and uninterrupted return to MPD after the complete batch.
- Activity timeline with 90-day retention, initial-import summaries, playback completions, episode links and per-browser unseen badges.
- Full-width desktop player and GitHub logo link.
- Publish Alpine only, for amd64 and arm64.

## 1.0.0

First stable PlayPod release.

- RSS library, bookmarks, playback progress, editable queues and optional MPD.
- Separate browser playback, configurable sleep mode and random continuation.
- Integrated downloads, yt-dlp audio imports and read-only local media.
- German/English interface, local language preference and PWA entry points.
- Alpine default image with QuickJS-NG; optional Debian image.
- GHCR workflow for tested amd64/arm64 images, triggered by GitHub Releases.
- Existing SQLite data and API v1/Node-RED playback behavior are preserved.
