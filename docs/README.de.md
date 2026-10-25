# PlayPod 1.0

Selbst gehosteter Podcastplayer mit Browseroberfläche, optionalem MPD und separater Browserwiedergabe.

## Start

`.env.example` nach `.env` kopieren, `MPD_HOST` bei Bedarf setzen:

```sh
docker compose up -d --build
```

Oberfläche: `http://HOST:9393`. Ohne MPD_HOST steht ausschließlich Browserwiedergabe zur Verfügung. Feeds in der Bibliothek hinzufügen. Alpine ist Standard; Debian ist als Alternative enthalten:

```sh
docker compose -f compose.yml -f compose.debian.yml up -d --build
```

Beim Wechsel im bisherigen Projektverzeichnis bleiben und dasselbe Datenvolume verwenden. Datenbank und Downloads bleiben erhalten. Vor Updates eine Sicherung erstellen. Bereits vorhandene Daten werden weiterverwendet; die Versionsumstellung setzt nichts zurück.

## Bedienung

- Freie Ansagen: `POST /api/v1/announcements` mit `{"text":"Die Waschmaschine ist fertig."}`. PlayPod bestätigt sofort mit HTTP 202 und erledigt TTS und Wiedergabe im Hintergrund. Die bestehende `TTS_AUDIO_URL` bleibt unverändert. Weitere Ansagen werden nacheinander abgespielt; Podcast und Sleep-Timer setzen erst nach der gesamten Ansagefolge fort. Statusabfragen sind optional.
- Aktivität zeigt neue Episoden und Wiedergabeabschlüsse aus MPD und Browser mit Zeitpunkt und Direktlink zur Episode. Erstimporte werden zusammengefasst. Die Historie bleibt 90 Tage erhalten; gelöschte Episoden behalten ihren Text ohne Link. Bestehende Episoden werden beim Update nicht nachgetragen.
- Die Zahl an „Aktivität“ zeigt ungesehene Ereignisse (bis „99+“). Beim Öffnen der Ansicht werden sie als gesehen gespeichert, getrennt pro Browser. Die Historie selbst ist geräteübergreifend.
- Normale Wiedergabe: Timer aus; Stop nach leerer Queue.
- Einschlafen: konfigurierte Laufzeit (initial 15 Minuten), Queue zuerst, danach Zufall aus allen oder nicht vollständig gehörten Episoden. Zufallsfolgen beginnen bei 0:00; gezielt gewählte und Queue-Folgen setzen fort.
- UI-Pause hält die Restzeit an, Fortsetzen behält sie einschließlich Verlängerungen. Next und gezielter Episodenstart setzen die gewählte Dauer neu. „Einschlafmodus beenden“ pausiert die Wiedergabe und deaktiviert Timer/Zufall.
- Bibliothek: Podcast links auswählen; mobil stehen Podcast und Episodenfilter als Auswahlfelder über der Liste. Abspielen und Anhängen sind direkt erreichbar, weitere Aktionen im Drei-Punkte-Menü.
- Sprache unter Einstellungen → Sprache: automatisch, Deutsch oder English. Die Wahl wird pro Browser gespeichert. Podcastinhalte und externe Diagnosen bleiben in ihrer Originalsprache.
- Browserplayer und MPD haben getrennte Warteschlangen/Timer. Das Umschalten startet keine Wiedergabe. Browseraudio wird beim Wechsel zurück zu MPD pausiert.
- Lokale Kopien über das Episodenmenü löschen; am ausgewählten Podcast „Gehörte Downloads löschen“ nutzen. Speicherverbrauch und verwaiste Dateien stehen unter Einstellungen. Gerade verwendete Kopien werden ausgelassen; Episoden, Merker und Hörfortschritt bleiben erhalten.
- RSS-Downloads, YT-Audioimporte und externe lokale Verzeichnisse werden im selben Container verwaltet. Externe Dateien werden nur gelesen. Beim Löschen einer lokalen Kopie bleiben Episode, Merker und Fortschritt erhalten.

Die PWA lässt sich über das Browsermenü installieren (HTTPS oder localhost). Offline-Audio ist nicht enthalten. Hintergrundwiedergabe und Timer im Browser hängen vom Betriebssystem ab; MPD wird serverseitig gesteuert.

Die vollständige Konfiguration, lokale Verzeichnisse und Entwicklungsbefehle stehen in [README.md](../README.md). [Node-RED/API](../NODE-RED.md), [GitHub-Releases](RELEASING.md).
