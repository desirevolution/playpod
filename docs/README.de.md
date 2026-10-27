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


### Automatische Feedaktualisierung

`RSS_INTERVAL_SECONDS` gibt das Intervall in Sekunden an (mindestens 60; 43200 entspricht 720 Minuten bzw. zwölf Stunden). Der Beginn der letzten Gesamtaktualisierung wird gespeichert. Ein Containerneustart setzt die Wartezeit nicht zurück: Ist der Termin überschritten, startet sofort eine Gesamtaktualisierung; andernfalls bleibt der bisherige Termin bestehen. Beim Upgrade ohne gespeicherten Gesamtlauf wird aus den bisherigen Feed-Abrufzeiten geplant. Noch nie geprüfte Feeds machen die erste Aktualisierung sofort fällig.

Ein manueller Gesamtlauf setzt den nächsten Termin neu. Das Aktualisieren nur eines Podcasts verschiebt ihn nicht. Ein bereits laufender Feedauftrag wird abgewartet; der Scheduler prüft spätestens nach einer Minute erneut. Fehler einzelner Feeds bleiben an den Podcasts sichtbar; der nächste reguläre Versuch folgt im eingestellten Intervall. Temporäre Schedulerfehler werden geloggt und nach einer Minute erneut versucht. Ohne RSS-Feeds erfolgt kein automatischer RSS-Auftrag.

Unter **Einstellungen → Technik und Verbindungen** stehen letzter Auftrag, nächster automatischer Termin und gegebenenfalls ein Hinweis auf einen inaktiven Scheduler. „Abgeschlossen“ beschreibt den Auftrag; Fehler einzelner Feeds werden daneben gezählt. Neue automatische Aufträge erscheinen im Log als `Automatische Feedaktualisierung gestartet`.

Beim Neustart unterbrochene Gesamtaktualisierungen werden erneut versucht, ohne ein weiteres komplettes Intervall zu warten.


### YouTube-Importe und Sammlungen

In **Bibliothek → Import** gibt es die Importarten Einzelvideo, YouTube-Playlist und YouTube-Kanal. Einzelimporte starten sofort einen Download und erscheinen unter **YouTube · Einzelimporte**. Playlists und Kanäle bilden eigene Sammlungen mit Herkunftskennzeichnung und Vorschaubildern. Sie werden im gleichen Intervall wie RSS (`RSS_INTERVAL_SECONDS`) geprüft, ohne automatisch Audiodateien herunterzuladen.

Beim ersten Import kann eine Anzahl (Vorgabe 50) oder „Alle“ gewählt werden. Kanäle verwenden ihre neuesten Videos, Playlists die Playlist-Reihenfolge. Der erste Abgleich merkt sich auch die zunächst nicht importierten IDs: Spätere Prüfungen ergänzen neue Videos und laden nicht ungefragt den restlichen alten Katalog nach. Shorts sowie laufende und geplante Livestreams werden ausgeschlossen. Abgeschlossene Livestream-Aufzeichnungen sind erlaubt. Private/gelöschte Einträge werden nicht neu importiert. Ein gescheiterter oder erkennbar unvollständiger Abruf darf keine Einträge entfernen.

**Anhängen** und **Für später merken** laden YouTube-Episoden bei Bedarf herunter. Bereits laufende oder fertige Downloads werden wiederverwendet. RSS-Episoden werden weiterhin gestreamt. Das Entfernen eines Merkers oder Warteschlangeneintrags bricht keinen Download ab. Random verwendet nur fertige YouTube-Downloads und keine ausgeblendeten Einträge.

Erreicht die Wiedergabe einen wartenden Download, pausiert der Player einschließlich Sleep-Timer, bis die Datei bereitsteht. Downloadfehler werden in der Warteschlange markiert und übersprungen. Pause beendet die wartende Startabsicht; der Download läuft weiter. Browser und MPD bleiben getrennte Wiedergabeziele.

Einzelimporte lassen sich samt Datei entfernen; „Lokale Kopie löschen“ behält normalerweise den Katalogeintrag. Playlist-/Kanalepisoden lassen sich ausblenden und über den Filter **Ausgeblendet** wiederherstellen. Nicht mehr verfügbare bzw. aus der Sammlung entfernte Videos bleiben erhalten, solange eine fertige lokale Datei existiert. Nach Löschen dieser Datei räumt der nächste erfolgreiche Sammlungsabgleich den nicht mehr verfügbaren Eintrag auf.

Das bestätigte Löschen einer YouTube-Sammlung entfernt alle ihre Einträge und Audiodateien. Duplikate und Dateien anderer Sammlungen bleiben unabhängig erhalten. Browserseitig verwendete Dateien müssen vor einer endgültigen Löschung freigegeben werden; externe Medienverzeichnisse werden niemals gelöscht. Die Cover sind externe Vorschaubild-URLs, keine lokal gespeicherten Bilddateien.

Das Datenbankschema wird auf Version 6 erweitert. Vor dem Upgrade einer vorhandenen Datenbank entsteht eine Sicherung mit der Endung `.before-v6.sqlite3`.


### Player, Zufallswiedergabe und Timer

Wiedergabestatus und der Umschalter **In diesem Browser abspielen** befinden sich direkt in der Player-Kachel. Die übrigen Ansichten zeigen diese Steuerung nicht im Seitenkopf. Ohne aktive Episode zeigt der Player eine Auswahlhilfe statt eines Buchstaben-Covers; nicht verfügbare Seek-/Sprung-/Merker-Steuerungen werden in diesem Zustand ausgeblendet.

Neben der Timer-Auswahl schaltet **Zufallswiedergabe** die konfigurierte Auswahl (alle oder ungehört) ein bzw. aus. Der Schalter verändert keine Timer-Dauer und startet nicht automatisch. Mit aktivierter Zufallswiedergabe kann **Play** auch ohne aktuelle Episode starten; die Warteschlange hat weiterhin Vorrang.

**Nächste** behält jetzt die verbleibende Timer-Zeit einschließlich +5-Minuten-Verlängerungen bei. Auch die Titelvorbereitung/-ansage bei manuellem „Nächste“ verbraucht diese Restzeit nicht. Ein abgelaufener Timer wird dadurch nicht neu gestartet. Ein explizites API-`timer:"default"` wählt weiterhin bewusst die volle Vorgabe. Das gezielte Starten einer einzelnen Episode und die API-Play/Toggle-Regeln bleiben unverändert.


### YouTube-Sammlung ohne Episoden

Nach einem Update die betroffene Sammlung auswählen und im Sammlungsmenü **Aktualisieren** ausführen. Frühere leere Importe werden beim nächsten erfolgreichen Abgleich erneut anhand ihrer Importgrenze gefüllt, ohne die Sammlung zu löschen. Bereits entdeckte IDs werden nicht pauschal als importiert behandelt. Temporär nicht verfügbare Videos können später nachkommen; bewusst durch die Erstimportgrenze ausgelassene Videos bleiben dagegen ausgeschlossen. Bei bestehenden, bereits gefüllten Alt-Sammlungen wird die bisherige Grenze beibehalten.

Bei einer leeren Sammlung zeigt die Bibliothek nach erfolgreichem Abruf die Anzahl gefundener, durch Shorts/Live-Filter ausgeschlossener, nicht verfügbarer und durch die Importgrenze ausgelassener Einträge. Abruffehler werden mit konkretem yt-dlp-Fehler am Feed angezeigt, statt nur als generischer RSS-Fehler. Diese Meldung bzw. der Playlist-Link helfen bei der Diagnose. Ein leeres Extraktionsergebnis trotz gemeldeter Videoanzahl gilt als Fehler und entfernt keine bestehenden Episoden. Pro erfolgreichem Abgleich werden die Zähler außerdem ins Backend-Log geschrieben.


### Pause und Wiedergabeende

Ein eigener Stop-Button ist nicht erforderlich: Pause hält Wiedergabe und UI-Timer an und behält die Position. Nach einer fertigen Episode ohne Fortsetzung zeigt der Player „Wiedergabe beendet“, sonst bei fehlender Wiedergabe „Keine Wiedergabe“. Die API-State-Werte bleiben unverändert. Im leeren Player führt der einzige Episoden-Auswahlzugang über die Warteschlange; der doppelte Button in der Player-Kachel entfällt.
