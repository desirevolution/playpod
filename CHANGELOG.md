# Changelog

## Unreleased
- Detailsdialog: Schließen-Button bleibt bei langen Titeln rechts oben; Cover wird angezeigt. YouTube-Titel/Beschreibung/Cover werden ohne Audiodownload in der aktuellen App-Sprache nachgeladen und getrennt für Deutsch/Englisch zwischengespeichert. Ladezustand, Wiederholung bei Fehlern und Schutz vor verspäteten Antworten nach Schließen/Sprachwechsel.
- Abgeschlossene YouTube-Livestream-Aufzeichnungen (was_live/post_live) werden importiert und heruntergeladen; nur Shorts sowie laufende/geplante Streams bleiben ausgeschlossen. Doppelte Auswahlaktion im leeren Player entfernt, Zugang über Warteschlange bleibt. Aussagekräftigere Wiedergabe-Endzustände ohne zusätzlichen Stop-Button.

- YouTube-Abgleich: Leere Altimporte lassen sich durch erneutes Aktualisieren reparieren; entdeckte IDs sind nicht länger pauschal vom späteren Import ausgeschlossen. Absichtlich ausgelassene Videos der Erstimportgrenze werden getrennt gespeichert. Diagnose für leere Sammlungen und konkrete YouTube-Abruffehler.

- Wiedergabestatus und Browserziel in Player-Kachel integriert; neuer leerer Zustand ohne Buchstaben-Cover. Zufallsschalter neben Timer-Auswahl mit Start aus leerem Player.
- „Nächste“ erhält Timer-Restzeit und Verlängerungen und friert diese bei Titelansagen ein. Ein explizites API-timer:default wählt weiterhin die volle Vorgabe.

- YouTube-Einzelimporte, Playlist- und Kanalabonnements mit Covern und Importgrenze/Alle; regelmäßiger Metadatenabgleich ohne Audiodownload, Shorts/Livestreams ausgeschlossen.
- Downloads beim Anhängen/Merken, vorbereitende Wiedergabe mit eingefrorenem Timer, Ausblenden/Wiederherstellen und Entfernen von Einzelimporten bzw. Sammlungen samt Dateien. Schema 6 mit automatischer Sicherung.
- RSS-Wiederanlauf erkennt auch den tatsächlichen Status „interrupted“ nach einem Prozessneustart.

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
