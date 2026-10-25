# PlayPod 1.0.0

PlayPod's first stable release brings podcast management, browser/MPD playback, editable queues, bookmarks, listening progress and sleep mode into one self-hosted application.

- German and English interface with saved language selection.
- RSS downloads, yt-dlp audio imports and read-only local folders in one container.
- Installable PWA with player/sleep/library shortcuts.
- Alpine and QuickJS-NG by default; Debian is available with `-debian` tags.
- Versioned REST API, Node-RED controls, optional MQTT and audio-URL title announcements.

Containers: `ghcr.io/<owner>/<repository>:1.0.0` and `:1.0.0-debian`, each for amd64 and arm64. The publish workflow uses the repository's actual name.

Existing installations: keep your Compose project name, `.env` and data volume. No reset is required. Language selection is available in Settings. Central Node-RED playback calls remain compatible. Back up your database before updating.

The PWA needs the server for library/audio access; device offline audio is not included. Browser background playback and timer execution depend on the browser/OS. Configure MPD for server-controlled playback.
