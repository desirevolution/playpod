# Changelog

## Unreleased
- Automatische RSS-Aktualisierung berücksichtigt den gespeicherten letzten Gesamtlauf statt nach jedem Neustart erneut das ganze Intervall abzuwarten. Überfällige Läufe werden beim Start nachgeholt; temporäre Schedulerfehler werden protokolliert und erneut versucht. Nächster Termin und Schedulerstatus in den Einstellungen.

- Allgemeine Layoutprüfung: kompakte Einstellungsfelder, umbrechende Abschnittsköpfe und Hilfstexte mit Lesebreite; stabile Scrollleistenbreite gegen seitliches Springen.

- Mini-Player: im Inhaltsbereich zentriert, maximal 1080px breit, kompakte Covergröße, Titel-Tooltip und dezente Fortschrittslinie.

- Große Bildschirme: zentrierte Inhaltsbreite (Player/Bibliothek 1440px, Aktivität 1120px, Einstellungen 1040px) und feste Cover-Spalte im Desktop-Player.

- Bibliothek: „Alle Podcasts“ als Auswahl, mobile Podcast-Liste mit Cover und Namen statt Dropdown; Tastaturhilfe auf Mobilgeräten ausgeblendet.


- Redesign with warm neutral surfaces, restrained accents, horizontal desktop player, compact inactive sleep mode, Library navigation, mobile action sheets and reduced help text.
- Move download actions to episode/podcast scope and storage maintenance to Settings; protect MPD and recently active browser copies during cleanup.

- Scale desktop player artwork and title with the card, show app-install help only in the mobile layout and stack link-import form fields/actions to prevent overlap.

- Use full width across all views, split desktop playback columns 60:40, place playback status above the target switch and hide inactive timer readouts.

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
