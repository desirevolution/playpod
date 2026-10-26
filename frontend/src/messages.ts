// German source messages are lookup keys; keep placeholders identical in all languages.
export const english: Record<string, string> = {
  "Bereit zum Abspielen": "Ready to play",
  "Play startet die Warteschlange oder eine passende zufällige Episode.":
    "Play starts the queue or a matching random episode.",
  "Wähle eine Episode oder aktiviere die Zufallswiedergabe.":
    "Choose an episode or enable random playback.",
  Zufallswiedergabe: "Random playback",
  An: "On",
  "Pause und „Nächste“ behalten die verbleibende Timer-Zeit bei. Zufallswiedergabe greift, wenn die Warteschlange leer ist.":
    "Pause and Next preserve the remaining timer. Random playback is used when the queue is empty.",

  Sammlungsaktionen: "Collection actions",
  "Sammlung oder Episode suchen …": "Search collection or episode \u2026",
  "Sammlung oder Episode suchen": "Search collection or episode",

  "Download fehlgeschlagen oder abgebrochen": "Download failed or cancelled",
  "Manuell übersprungen": "Skipped manually",
  "Wartet auf Download": "Waiting for download",
  "Download wird vorbereitet. Wiedergabe und Sleep-Timer warten.":
    "Preparing download. Playback and the sleep timer are waiting.",
  "Import entfernen?": "Remove import?",
  "Eintrag und heruntergeladene Audiodatei endgültig löschen?":
    "Permanently delete this entry and its downloaded audio file?",
  "Sammlung endgültig löschen?": "Permanently delete collection?",
  "„{title}“ mit allen Einträgen und heruntergeladenen Audiodateien endgültig löschen?":
    "Permanently delete “{title}”, all its entries and downloaded audio files?",
  "YouTube importieren": "Import YouTube",
  "Sammlung hinzugefügt. Einträge werden ohne Download eingelesen.":
    "Collection added. Entries are imported without downloading audio.",
  "Einzelimporte werden direkt heruntergeladen. Playlists und Kanäle werden regelmäßig ohne Audiodownload eingelesen. Shorts und Livestreams werden ausgeschlossen.":
    "Single imports are downloaded immediately. Playlists and channels are checked regularly without downloading audio. Shorts and livestreams are excluded.",
  Importart: "Import type",
  "Einzelnes Video": "Single video",
  "YouTube-Playlist": "YouTube playlist",
  "YouTube-Kanal": "YouTube channel",
  "Alle vorhandenen Videos einlesen": "Import all existing videos",
  "Anzahl beim ersten Import": "Number for initial import",
  "Beim Kanal werden die neuesten Videos gewählt, bei Playlists die ersten Einträge in Playlist-Reihenfolge. Spätere neue Videos werden ergänzt.":
    "Channels import the latest videos; playlists import their first entries in playlist order. New videos are added on subsequent checks.",
  "Sammlung hinzufügen": "Add collection",
  "Alle Sammlungen": "All collections",
  "Sammlung auswählen": "Select collection",
  Sammlungen: "Collections",
  Ausgeblendet: "Hidden",
  "Import entfernen": "Remove import",
  "Wieder einblenden": "Unhide",
  Ausblenden: "Hide",
  "Sammlung löschen": "Delete collection",
  "YT-Playlist": "YT playlist",
  "YT-Kanal": "YT channel",
  Einzelimporte: "Single imports",

  Import: "Import",
  Podcast: "Podcast",
  Filter: "Filter",
  "Keine lokalen Verzeichnisse eingerichtet.": "No local folders configured.",
  "Einrichtung und Dateiverwaltung": "Setup and file management",
  "Keine gehörten Downloads vorhanden.": "No finished downloads to remove.",
  "Gehörte Downloads löschen?": "Delete finished downloads?",
  "{count} lokale Kopien löschen? Episoden, Merker und Hörfortschritt bleiben erhalten. Verwendete Dateien werden ausgelassen.":
    "Delete {count} local copies? Episodes, bookmarks and listening progress are kept. Files in use are skipped.",
  "{deleted} Kopien gelöscht · {skipped} verwendet · {failed} fehlgeschlagen":
    "{deleted} copies deleted · {skipped} in use · {failed} failed",
  "Alle Einträge aus „{title}“ samt Merkern, Hörfortschritt und Warteschlangeneinträgen entfernen? Eine zugehörige Wiedergabe stoppt. Die Sammlung und ihr Favoritenstatus bleiben erhalten. Audiodateien bleiben auf dem Datenträger und können unter Einstellungen als verwaiste Dateien aufgeräumt werden.":
    "Remove all entries from “{title}”, including bookmarks, listening progress and queue entries? Associated playback stops. The collection and its favorite setting are kept. Audio files stay on disk and can be removed as orphaned files in Settings.",
  Bibliothek: "Library",
  Einstellungen: "Settings",
  "Hinweise zum Einschlafmodus": "About sleep mode",
  "Downloads und Speicher": "Downloads and storage",
  "Keine verwaisten Downloads.": "No orphaned downloads.",
  "Was wird gelöscht?": "What gets deleted?",
  "Nur lokale Downloadkopien werden gelöscht. Episoden, Merker und Hörfortschritt bleiben erhalten. Externe Dateien werden nur gelesen.":
    "Only downloaded copies are deleted. Episodes, bookmarks and listening progress are kept. External files are read-only.",
  "Technik und Verbindungen": "Technical details and connections",
  "Über das Browsermenü installieren oder zum Startbildschirm hinzufügen (HTTPS oder localhost).":
    "Install using the browser menu or add to your home screen (HTTPS or localhost).",
  "Link importieren": "Import link",
  Podcasts: "Podcasts",
  Fehler: "Error",
  "Podcast auswählen": "Select podcast",
  "Quellen prüfen": "Check sources",
  "Episoden filtern": "Filter episodes",
  "Weitere Aktionen": "More actions",
  "Beschreibung ansehen": "View description",
  "Gehörte Downloads löschen": "Delete finished downloads",
  "Podcast-Aktionen": "Podcast actions",
  Aktualisieren: "Refresh",
  "Wird gerade verwendet": "Currently in use",
  "Download abbrechen": "Cancel download",
  "Timer-Hinweise": "About the timer",
  "Warteschlange leer.": "Queue is empty.",
  Wiedergaberegeln: "Playback rules",
  "Episoden auswählen": "Choose episodes",
  "Wähle eine Episode in der Bibliothek.": "Choose an episode in the library.",
  "Letzte 90 Tage": "Last 90 days",
  "Diese lokale Kopie wird in einem Browser verwendet":
    "This local copy is in use in a browser",
  "{count} lokale Kopie": "{count} local copy",
  "{count} lokale Kopien": "{count} local copies",
  Ansage: "Announcement",
  "MPD konnte die Episode nach der Ansage nicht fortsetzen":
    "MPD could not resume the episode after the announcement",
  "Zeitlimit beim Fortsetzen nach der Ansage erreicht":
    "Timed out while resuming after the announcement",
  "Ansage beenden und nächste Episode starten":
    "End announcement and start the next episode",
  "Eine Ansage läuft bereits": "An announcement is already playing",
  "Eine Ansage wird bereits vorbereitet":
    "An announcement is already being prepared",
  "Keine TTS-Audiodatei erhalten. TTS_AUDIO_URL prüfen.":
    "No TTS audio file received. Check TTS_AUDIO_URL.",
  "MPD konnte die Ansage nicht starten": "MPD could not start the announcement",
  "Ansage fehlgeschlagen; Wiederherstellung der Wiedergabe steht noch aus":
    "Announcement failed; playback restoration is still pending",
  Aktivität: "Activity",
  "{count} ungesehene Ereignisse": "{count} unseen events",
  "Aktivität filtern": "Filter activity",
  "Neue Episoden": "New episodes",
  "Ereignisse der letzten 90 Tage. Zeitpunkte entsprechen deiner lokalen Zeitzone.":
    "Events from the last 90 days. Times are shown in your local time zone.",
  "Aktivität wird geladen …": "Loading activity …",
  "Zu Ende gehört": "Finished listening",
  "Podcast hinzugefügt": "Podcast added",
  "Neue Episode": "New episode",
  Browser: "Browser",
  "Inzwischen gelöscht": "Since deleted",
  "Noch keine Ereignisse für diesen Filter.": "No events for this filter yet.",
  "PlayPod auf GitHub öffnen (neuer Tab)": "Open PlayPod on GitHub (new tab)",
  "Audio kann im Browser nicht abgespielt werden. Quelle oder Format prüfen; gegebenenfalls herunterladen.":
    "Audio cannot be played in this browser. Check the source or format, or download the episode.",
  "Zum Starten der Browserwiedergabe bitte erneut Abspielen drücken.":
    "Press Play again to start browser playback.",
  "Audio konnte nicht gestartet werden": "Audio could not be started",
  "Browserwiedergabe benötigt einen Klick auf Abspielen.":
    "Click Play to allow audio playback in this browser.",
  "Episode konnte im Browser nicht gestartet werden":
    "The episode could not be started in this browser",
  "Warteschlange ist leer": "The queue is empty",
  "Keine passende Episode verfügbar": "No matching episode available",
  "Keine weitere im Browser abspielbare Episode vorhanden":
    "No further playable episode available in this browser",
  "Kein Überspringen zum Rückgängigmachen": "No skipped episode to restore",
  "Sleep-Timer ist ausgeschaltet": "The sleep timer is off",
  "Maximal 200 Einträge pro Browserqueue":
    "A browser queue can contain up to 200 episodes",
  "Warteschlange wurde geändert": "The queue has changed",
  "Browserbefehl nicht unterstützt": "Browser command not supported",
  Modusansage: "Mode announcement",
  Titelansage: "Title announcement",
  "Modusansage beenden und nächste Episode starten":
    "End announcement and start the next episode",
  "Ansage überspringen und Episode starten":
    "Skip announcement and start episode",
  "Nächste Episode aus der Warteschlange": "Next episode in the queue",
  "Nächste Episode: Warteschlange zuerst, sonst zufällig":
    "Next episode: queue first, then random",
  "Anfrage fehlgeschlagen": "Request failed",
  "Verbindung zu PlayPod unterbrochen. Status wird erneut abgefragt.":
    "Connection to PlayPod lost. Retrying status updates.",
  "Titelansage gestartet.": "Title announcement started.",
  "Wiedergabe gestartet.": "Playback started.",
  "An Warteschlange angehängt.": "Added to queue.",
  "Bereits in der Warteschlange.": "Already in the queue.",
  "Download vorgemerkt.": "Download queued.",
  "Download wird abgebrochen.": "Cancelling download.",
  "Merker entfernt.": "Bookmark removed.",
  "Für später gemerkt.": "Bookmarked for later.",
  "Lokaler Verzeichnisscan gestartet.": "Local folder scan started.",
  "Feedaktualisierung gestartet.": "Feed refresh started.",
  "Lokale Verzeichnisse werden eingelesen.": "Scanning local folders.",
  "Lokale Kopie löschen?": "Delete local copy?",
  Episode: "Episode",
  "Zum erneuten Abspielen muss der Seitenlink wieder heruntergeladen werden.":
    "Download the page link again to play it.",
  "Feedepisoden werden anschließend wieder gestreamt.":
    "Feed episodes will be streamed again.",
  "Lokale Kopie gelöscht.": "Local copy deleted.",
  "Verwaiste Downloads löschen?": "Delete orphaned downloads?",
  "Es werden nur nicht mehr zugeordnete Dateien im PlayPod-Downloadordner entfernt. Externe Medienverzeichnisse bleiben unverändert.":
    "Only unassigned files in the PlayPod download folder will be removed. External media folders are left unchanged.",
  "Keine ungehörten Episoden ohne Download vorhanden.":
    "No unplayed episodes without downloads found.",
  "Feedepisoden herunterladen?": "Download feed episodes?",
  "Pro Start werden höchstens 1000 Episoden vorgemerkt.":
    "Up to 1000 episodes can be queued at a time.",
  "Warteschlange leeren?": "Clear queue?",
  "Die wartenden Einträge werden entfernt. Die aktuelle Wiedergabe läuft weiter.":
    "Queued entries will be removed. The current episode keeps playing.",
  "Importliste leeren?": "Clear import list?",
  "Podcast endgültig löschen?": "Permanently delete podcast?",
  "Aus Katalog entfernen?": "Remove from library?",
  "Die Audiodatei bleibt unverändert auf dem Datenträger. Ein erneuter Scan nimmt sie wieder auf. Merker und Fortschritt dieses Eintrags werden entfernt; eine zugehörige Wiedergabe stoppt.":
    "The audio file stays on disk. Scanning again imports it again. Bookmarks and progress for this entry will be removed; playback of this episode stops.",
  "Hauptnavigation mobil": "Mobile navigation",
  Hauptnavigation: "Main navigation",
  Player: "Player",
  Management: "Management",
  Config: "Settings",
  "Verbindung wird aufgebaut": "Connecting",
  "In diesem Browser abspielen": "Play in this browser",
  "Dieser Browser": "This browser",
  "Eigene Queue · MPD läuft unabhängig":
    "Separate queue · MPD continues independently",
  läuft: "running",
  "Wiedergabe läuft": "Playing",
  Pausiert: "Paused",
  Gestoppt: "Stopped",
  "Ohne Datum": "No date",
  Verbindungen: "Connections",
  "Feedaktualisierung alle": "Refresh feeds every",
  "Minuten.": "minutes.",
  Version: "Version",
  "Verbindungen werden über Umgebungsvariablen konfiguriert. „Konfiguriert“ bei TTS ist kein Erreichbarkeitstest.":
    "Connections are configured using environment variables. A configured TTS endpoint is not a connectivity test.",
  Einschlafmodus: "Sleep mode",
  "Laufzeit in Minuten": "Duration in minutes",
  "Wenn die Warteschlange leer ist": "When the queue is empty",
  "Zufällig · nicht vollständig gehört": "Random · not fully played",
  "Zufällig · alle Episoden": "Random · all episodes",
  "Zufällige Episoden starten von vorne. Angefangene Folgen zählen als nicht vollständig gehört. Ohne passende Folge stoppt die Wiedergabe. Änderungen gelten beim nächsten Aktivieren; laufende Wiedergabe bleibt unverändert.":
    "Random episodes start from the beginning. Partially played episodes count as not fully played. Playback stops if no episode matches. Changes apply the next time sleep mode is started.",
  "PlayPod als App": "PlayPod as an app",
  "Über das Browsermenü installieren oder zum Startbildschirm hinzufügen (HTTPS oder localhost). Die App enthält Direkteinstiege zu Player, Einschlafen und Management. Ein Direkteinstieg startet kein Audio.":
    "Install from the browser menu or add to your home screen (HTTPS or localhost). Shortcuts open the player, sleep mode or management without starting audio.",
  "Ohne Verbindung zum Server gibt es keine Audio-Wiedergabe. Updates unterbrechen keine laufende Episode; die App bei Bedarf vollständig schließen und neu öffnen.":
    "Audio playback needs a connection to the server. Updates do not interrupt an episode; close and reopen the app when needed.",
  "Episoden herunterladen": "Download episodes",
  "Im Management kannst du Feedepisoden herunterladen und den Fortschritt verfolgen. Ein Download läuft gleichzeitig. Fertige Dateien werden beim nächsten Start bevorzugt lokal abgespielt; die laufende Wiedergabe bleibt erhalten.":
    "Download feed episodes and follow their progress in Management. One download runs at a time. Completed downloads are used on the next start; current playback continues.",
  "Downloads liegen im Datenvolume von PlayPod. Externe Verzeichnisse bleiben nur lesbar. Bei nicht verfügbarer lokaler Kopie wird die Originalquelle verwendet.":
    "Downloads are stored in the PlayPod data volume. External folders are read-only. The original source is used if a local copy is unavailable.",
  "Lokale Medien": "Local media",
  "Externe Verzeichnisse werden nur gelesen.":
    "External folders are read-only.",
  "Jetzt einlesen": "Scan now",
  "Dateien bleiben beim Entfernen aus dem Katalog auf dem Datenträger. Fehlende Dateien werden beim Einlesen gekennzeichnet.":
    "Removing a library entry leaves its file on disk. Missing files are marked during a scan.",
  Verbunden: "Connected",
  "Nicht erreichbar": "Unreachable",
  Wiedergabe: "Playback",
  "Nur Browser": "Browser only",
  Bereit: "Ready",
  Deaktiviert: "Disabled",
  "Nicht verbunden": "Disconnected",
  "Vor Episode über MPD": "Before episode via MPD",
  Konfiguriert: "Configured",
  "Letzte Aktualisierung:": "Last refresh:",
  "Feed(s) fehlgeschlagen": "feed(s) failed",
  "Noch keine Feedaktualisierung ausgeführt.": "No feed refresh yet.",
  "Einschlaf-Vorgaben gespeichert.": "Sleep defaults saved.",
  "Speichert …": "Saving …",
  Speichern: "Save",
  "Zum lokalen Abspielen MEDIA_BASE_URL auf die für MPD erreichbare PlayPod-Adresse setzen.":
    "Set MEDIA_BASE_URL to the PlayPod address reachable by MPD for local playback.",
  "Downloads bereit": "Downloads ready",
  "Downloads derzeit nicht verfügbar.": "Downloads currently unavailable.",
  "Verzeichnisse geprüft": "folders checked",
  "Einträge · Nur lesen": "entries · Read-only",
  Erreichbar: "Available",
  "Zuletzt eingelesen:": "Last scan:",
  "Noch kein Verzeichnis eingerichtet. MEDIA_ROOTS und einen passenden Docker-Mount konfigurieren.":
    "No folders configured. Set MEDIA_ROOTS and the matching Docker mounts.",
  "Lokale Dateien werden direkt in diesem Browser abgespielt.":
    "Local files play directly in this browser.",
  "Medienadresse für MPD:": "Media address for MPD:",
  "Für lokale Wiedergabe über MPD MEDIA_BASE_URL auf die für MPD erreichbare PlayPod-Adresse setzen. Browserwiedergabe funktioniert ohne diese Angabe.":
    "For local playback via MPD, set MEDIA_BASE_URL to a PlayPod address reachable by MPD. Browser playback works without it.",
  "Dialog schließen": "Close dialog",
  "Downloads verwalten": "Manage downloads",
  "Video-/Audiolink hinzufügen": "Add video/audio link",
  "Podcast bearbeiten": "Edit podcast",
  "Podcast hinzufügen": "Add podcast",
  "Nicht erreichbare Episoden": "Unreachable episodes",
  "Von vorne": "From beginning",
  "Importierte Audiospur: Zum Abspielen wird eine heruntergeladene Kopie benötigt.":
    "Imported audio: download a copy before playing.",
  "Originalseite öffnen ↗": "Open original page ↗",
  "Lokale Datei:": "Local file:",
  "Aus Katalog entfernen": "Remove from library",
  "Als ungehört markieren": "Mark as unplayed",
  "Als gehört markieren": "Mark as played",
  Fortsetzen: "Resume",
  Abspielen: "Play",
  Abbrechen: "Cancel",
  Bestätigen: "Confirm",
  Anzeigename: "Display name",
  "Wird aus dem Feed übernommen": "Taken from the feed",
  "RSS-Feed-URL": "RSS feed URL",
  "Als Favorit markieren": "Mark as favorite",
  "Der Episodenkatalog wird beim Feedabruf aktualisiert. Der Anzeigename kann dabei durch den Feedtitel ersetzt werden.":
    "Refreshing the feed updates its episodes. The display name may be replaced by the feed title.",
  "Podcast gespeichert.": "Podcast saved.",
  "Podcast hinzugefügt. Feedabruf läuft.": "Podcast added. Refreshing feed.",
  "Originalquellen manuell prüfen. Es wird nichts automatisch gelöscht. Ein erreichbarer Server bestätigt noch nicht die vollständige Abspielbarkeit.":
    "Check original sources manually. Nothing is deleted automatically. An accessible server does not guarantee that an episode can be played in full.",
  Schließen: "Close",
  "geprüft ·": "checked ·",
  "Prüfung läuft": "Checking",
  Abgeschlossen: "Completed",
  Unterbrochen: "Interrupted",
  "Bitte Episoden auswählen.": "Select episodes first.",
  "Episoden endgültig löschen?": "Permanently delete episodes?",
  "Achtung: Die Auswahl enthält temporäre Fehler. Diese Quellen könnten weiterhin verfügbar sein.":
    "Warning: the selection includes temporary errors. These sources may still be available.",
  "Episode #": "Episode #",
  "· möglicherweise nur vorübergehend": "· possibly temporary",
  "Keine definitiv fehlenden Quellen gefunden.":
    "No definitely missing sources found.",
  "– nicht automatisch zum Löschen angeboten.":
    "– not automatically offered for deletion.",
  "Ausgewählte löschen": "Delete selected",
  "Erneut prüfen": "Check again",
  "Prüfung starten": "Start check",
  "Einzelnes YouTube-Video oder ein Video-/Audiolink einer weiteren von yt-dlp unterstützten Seite. Importiert wird ausschließlich die Audiospur, kein Video. Die Einträge erscheinen unter „YT-Importe“. Playlists, Kanäle und laufende Livestreams werden nicht importiert.":
    "A single YouTube video or a video/audio link from another yt-dlp supported site. Only audio is imported. Entries appear under “YT imports”. Playlists, channels and live streams are not imported.",
  "Video-/Audio-URL": "Video/audio URL",
  "Hinzufügen und herunterladen": "Add and download",
  "Link hinzugefügt. Audiospur wird heruntergeladen.":
    "Link added. Downloading audio.",
  "lokale Kopien ·": "local copies ·",
  frei: "free",
  "Löschen entfernt nur die lokale Kopie. Merker, Episode und Hörfortschritt bleiben erhalten. Dateien aus externen Verzeichnissen werden hier nicht gelöscht.":
    "Deleting removes only the local copy. The episode, bookmarks and progress are kept. Files in external folders are not deleted here.",
  "ohne Episodenzuordnung": "without an episode",
  "Verwaiste Dateien löschen": "Delete orphaned files",
  Heruntergeladen: "Downloaded",
  "Kopie gelöscht": "Copy deleted",
  "Audio wird vorbereitet": "Processing audio",
  "Download läuft": "Downloading",
  Wartet: "Queued",
  "Wird abgebrochen": "Cancelling",
  Abgebrochen: "Cancelled",
  "Datei fehlt": "File missing",
  "Lokale Kopie löschen": "Delete local copy",
  "Noch von MPD verwendet – zuerst Quelle wechseln.":
    "Still used by MPD – switch the source first.",
  "Erneut laden": "Download again",
  "Noch keine Downloads vorhanden.": "No downloads yet.",
  "Podcast oder Episode suchen …": "Search podcasts or episodes …",
  "Podcast oder Episode suchen": "Search podcasts or episodes",
  "Lokale Medien einlesen": "Scan local media",
  Aufräumen: "Clean up",
  "Podcasts und Importe": "Podcasts and imports",
  "Alle aktualisieren": "Refresh all",
  Episoden: "Episodes",
  Einträge: "entries",
  Zurück: "Back",
  von: "of",
  Weitere: "More",
  "Katalog wird geladen …": "Loading library …",
  Alle: "All",
  "Für später": "For later",
  Ungehört: "Unplayed",
  Angespielt: "Started",
  Gehört: "Played",
  Feedaktualisierung: "Feed refresh",
  "Lokale Verzeichnisse": "Local folders",
  "URL-Prüfung": "URL check",
  "Episoden ·": "episodes ·",
  "Favorit entfernen": "Remove favorite",
  Favorisieren: "Add favorite",
  "Lokales Verzeichnis": "Local folder",
  "YT-Importe · Audio": "YT imports · Audio",
  "Manuell importiert": "Imported manually",
  Aktualisiert: "Updated",
  "Noch nicht aktualisiert": "Not refreshed yet",
  "Verzeichnisse einlesen": "Scan folders",
  "Diesen Feed aktualisieren": "Refresh this feed",
  "Ungehörte herunterladen": "Download unplayed episodes",
  "Feed bearbeiten": "Edit feed",
  "Importliste leeren": "Clear import list",
  "Podcast löschen": "Delete podcast",
  "Keine Podcasts oder Episoden zur Suche gefunden.":
    "No matching podcasts or episodes found.",
  "Noch keine Podcasts oder Importe vorhanden. Podcast per RSS-URL oder Video-/Audiolink hinzufügen.":
    "No podcasts or imports yet. Add a podcast using its RSS URL or a video/audio link.",
  Anhängen: "Add to queue",
  "Dauer unbekannt": "Duration unknown",
  "Angespielt ·": "Started ·",
  "Lokale Datei": "Local file",
  "Datei noch nicht bereit": "File not ready yet",
  "Verzeichnis deaktiviert": "Folder disabled",
  "In Warteschlange": "In queue",
  "Quelle nicht erreichbar": "Source unreachable",
  "Merker entfernen": "Remove bookmark",
  "Für später merken": "Bookmark for later",
  "Keine Episoden für diesen Filter.": "No episodes match this filter.",
  "Heruntergeladen ·": "Downloaded ·",
  "Audio wird vorbereitet ·": "Processing audio ·",
  "Download ·": "Download ·",
  "Download wartet": "Download queued",
  "Download wird abgebrochen …": "Cancelling download …",
  "Lokale Kopie gelöscht": "Local copy deleted",
  "Download abgebrochen": "Download cancelled",
  "Download fehlgeschlagen": "Download failed",
  "Download abbrechen:": "Cancel download:",
  "Episode herunterladen:": "Download episode:",
  Herunterladen: "Download",
  Wiedergabeposition: "Playback position",
  "30 Sekunden zurück": "Back 30 seconds",
  "30 Sekunden vor": "Forward 30 seconds",
  "Sleep-Timer": "Sleep timer",
  Einschlafen: "Sleep",
  "Queue zuerst, danach": "Queue first, then",
  "+5 Min.": "+5 min",
  "Als Nächstes": "Up next",
  "Min.": "min",
  Leeren: "Clear",
  "Episoden entdecken": "Find episodes",
  "Leertaste: Play/Pause · ← / →: 30 Sekunden · ↑ / ↓: Lautstärke ±5 % · N: Nächste · P: Player":
    "Space: Play/Pause · ← / →: 30 seconds · ↑ / ↓: Volume ±5% · N: Next · P: Player",
  "Keine Episode ausgewählt": "No episode selected",
  "Keine aktive Episode": "No active episode",
  "Beschreibung ansehen ↗": "Show description ↗",
  "Wähle eine Episode im Management oder starte die Wiedergabe.":
    "Choose an episode in Management or start playback.",
  Originalquelle: "Original source",
  "Letztes Überspringen rückgängig": "Undo last skip",
  Pausieren: "Pause",
  "Für später gemerkt": "Bookmarked for later",
  "Nur Favoriten": "Favorites only",
  "Alle Podcasts": "All podcasts",
  "Nächste automatische Aktualisierung:": "Next automatic update:",
  "Automatische Feedaktualisierung ist nicht aktiv.":
    "Automatic feed updates are not active.",
  "Browser-Lautstärke": "Browser volume",
  "MPD-Lautstärke": "MPD volume",
  Aus: "Off",
  "· pausiert für Ansage": "· paused for announcement",
  "zufällig aus allen Episoden": "random from all episodes",
  "zufällig aus nicht gehörten Episoden": "random from unplayed episodes",
  "· pausiert": "· paused",
  "Einschlafen starten": "Start sleep mode",
  Pause: "Pause",
  "Einschlafmodus beenden": "End sleep mode",
  "Vorgaben ändern": "Edit defaults",
  "Noch nichts vorgemerkt.": "Nothing queued yet.",
  "Hänge im Management Episoden an.":
    "Add episodes to the queue in Management.",
  "Nach der Warteschlange stoppt die Wiedergabe.":
    "Playback stops after the queue.",
  "Danach zufällig aus nicht gehörten Episoden wählen und von vorne starten.":
    "Then choose randomly from episodes not fully played and start from the beginning.",
  "Danach zufällig aus allen Episoden wählen und von vorne starten.":
    "Then choose randomly from all episodes and start from the beginning.",
  "Ein aktiver Timer läuft bei automatischen Folgenwechseln weiter.":
    "The timer continues across automatic episode changes.",
  "Erneut freigeben": "Retry",
  "Jetzt abspielen": "Play now",
  "Eintrag entfernen": "Remove entry",
  "Player öffnen": "Open player",
  "Timer aus": "Timer off",
  abgeschlossen: "completed",
  "abgebrochen/fehlgeschlagen": "cancelled/failed",
  pausiert: "paused",
  Minuten: "minutes",
  "nach oben": "move up",
  "nach unten": "move down",
  "· ab Episode": "· from episode start",
  "Keine Beschreibung vorhanden.": "No description available.",
  Sprache: "Language",
  Automatisch: "Automatic",
  Deutsch: "Deutsch",
  English: "English",
  "{elapsed} von {duration}": "{elapsed} of {duration}",
  "Entfernt {title}": "Remove {title}",
  "Die Audiodatei von „{title}“ wird gelöscht. Episode, Merker und Hörfortschritt bleiben erhalten.":
    "The audio file for “{title}” will be deleted. The episode, bookmarks and progress are kept.",
  "{count} ungehörte Episoden werden nacheinander heruntergeladen. Bereits geladene oder vorgemerkte Folgen werden übersprungen. Die Gesamtgröße ist vorher nicht bekannt.":
    "{count} unplayed episodes will be downloaded in order. Completed or queued downloads are skipped. The total size is not known in advance.",
  "{count} Downloads vorgemerkt.": "{count} downloads queued.",
  "Alle Einträge aus „{title}“ samt Merkern, Hörfortschritt und Warteschlangeneinträgen entfernen? Eine zugehörige Wiedergabe stoppt. Die Sammlung und ihr Favoritenstatus bleiben erhalten. Audiodateien bleiben auf dem Datenträger und können unter „Downloads verwalten“ als verwaiste Dateien aufgeräumt werden.":
    "Remove all entries from “{title}”, including bookmarks, progress and queue entries? Playback of an affected episode stops. The collection and its favorite status are kept. Audio files stay on disk and can be removed as orphaned files in Manage downloads.",
  "„{title}“ samt Episoden, Merkern und Warteschlangeneinträgen löschen? Eine zugehörige Wiedergabe stoppt. Heruntergeladene Audiodateien bleiben bis zum Aufräumen verwaister Dateien erhalten.":
    "Delete “{title}”, its episodes, bookmarks and queue entries? Playback of an affected episode stops. Downloaded audio files remain until orphaned files are cleaned up.",
  "{count} Episoden samt Merkern und Queue-Einträgen löschen? Eine zugehörige laufende Episode wird gestoppt.":
    "Delete {count} episodes, including bookmarks and queue entries? Playback of an affected episode stops.",
  "YT-Importe": "YT imports",
  "Episode nicht gefunden": "Episode not found",
  "Warteschlange wurde inzwischen geändert. Bitte erneut versuchen.":
    "The queue has changed. Please try again.",
  "Ungültige Warteschlangenreihenfolge": "Invalid queue order",
  "MPD konnte die Episode nicht starten": "MPD could not start the episode",
  "MPD ist nicht erreichbar. Warteschlange bleibt unverändert.":
    "MPD is unreachable. The queue is unchanged.",
  "Episode konnte nicht gestartet werden": "The episode could not be started",
  "Keine abspielbare Episode vorhanden": "No playable episode available",
  "Keine unveränderte Überspringaktion zum Rückgängigmachen":
    "The last skip can no longer be undone",
  "MPD ist nicht erreichbar": "MPD is unreachable",
  "MPD stellt keine regelbare Lautstärke bereit":
    "MPD does not provide volume control",
  "MPD konnte die Modusansage nicht starten":
    "MPD could not start the mode announcement",
  "MPD konnte die Episode nach der Modusansage nicht fortsetzen":
    "MPD could not resume after the announcement",
  "Zeitlimit beim Fortsetzen nach der Modusansage erreicht":
    "Timed out resuming after the announcement",
  "MPD nicht konfiguriert": "MPD is not configured",
  "Keine gültige Audio-URL erhalten": "No valid audio URL received",
  "Zeitlimit für yt-dlp überschritten": "yt-dlp timed out",
  "Temporäre Dateien überschreiten das Downloadlimit":
    "Temporary files exceed the download limit",
  "yt-dlp hat keine Audiodatei erzeugt": "yt-dlp did not produce an audio file",
  "Ungültige oder zu große Audiodatei":
    "Invalid audio file or download size exceeded",
  "Eine HTTP- oder HTTPS-Adresse ist erforderlich":
    "An HTTP or HTTPS URL is required",
  "App wird beendet": "The app is shutting down",
  "Feed ist zu groß": "The feed is too large",
  "Kein RSS-/Atom-Feed": "Not an RSS or Atom feed",
  "Diese Datenbank benötigt eine neuere PlayPod-Version.":
    "This database requires a newer PlayPod version.",
  "MEDIA_BASE_URL darf keine Query oder Fragment enthalten":
    "MEDIA_BASE_URL must not contain a query or fragment",
  "MEDIA_ROOTS muss ein JSON-Objekt aus Namen und absoluten Pfaden sein":
    "MEDIA_ROOTS must be a JSON object mapping names to absolute paths",
  "MEDIA_ROOTS muss ein JSON-Objekt sein": "MEDIA_ROOTS must be a JSON object",
  "MEDIA_ROOTS: Namen nur Buchstaben/Ziffern/_/-, Pfade müssen absolut sein":
    "MEDIA_ROOTS: names may only contain letters, digits, underscores and hyphens; paths must be absolute",
  "Lokales Verzeichnis ist nicht konfiguriert":
    "Local folder is not configured",
  "Ungültiger Medienpfad": "Invalid media path",
  "Lokale Datei ist nicht verfügbar": "Local file is unavailable",
  "Lokale Datei nicht verfügbar": "Local file unavailable",
  "Lokale Datei ist leer": "Local file is empty",
  "Datei wurde geändert. Bitte lokale Medien erneut einlesen.":
    "The file has changed. Please scan local media again.",
  "Lokale Datei ist nicht erreichbar": "Local file is unreachable",
  "Seitenlink zuerst herunterladen, bevor er abgespielt werden kann":
    "Download the page link before playing it",
  "MEDIA_BASE_URL fehlt: interne, für MPD erreichbare PlayPod-Adresse eintragen":
    "MEDIA_BASE_URL is missing: enter the internal PlayPod URL reachable by MPD",
  "Keine verfügbare Wiedergabequelle": "No playback source available",
  "Keine Wiedergabequelle verfügbar": "No playback source available",
  "Scan unterbrochen": "Scan interrupted",
  "Verzeichnis nicht erreichbar": "Folder unreachable",
  "Lokaler Katalog fehlt": "Local library missing",
  "Eintrag existiert bereits oder wurde inzwischen gelöscht":
    "The entry already exists or has been deleted",
  "Ungültige Anfrage": "Invalid request",
  "Interner Fehler bei der Verarbeitung": "Internal processing error",
  "MPD-Befehl fehlgeschlagen": "MPD command failed",
  "timer ist nur bei play, toggle und next erlaubt":
    "timer is only supported for play, toggle and next",
  "timer=preserve ist nur bei play und toggle erlaubt":
    "timer=preserve is only supported for play and toggle",
  "when_queue_empty ist nur bei play, toggle und next erlaubt":
    "when_queue_empty is only supported for play, toggle and next",
  "Podcast nicht gefunden": "Podcast not found",
  "Die Linksammlung hat keine veränderbare Feedadresse":
    "The import collection does not have an editable feed URL",
  "Lokale Verzeichnisse werden über MEDIA_ROOTS konfiguriert":
    "Configure local folders using MEDIA_ROOTS",
  "Lokale Sammlung über MEDIA_ROOTS deaktivieren. Einzelne Einträge können aus dem Katalog entfernt werden.":
    "Disable a local collection using MEDIA_ROOTS. Individual entries can be removed from the library.",
  "Sammlung nicht gefunden": "Collection not found",
  "Nur die Linkimportliste kann geleert werden":
    "Only the import list can be cleared",
  "Einzelne Seitenlinks haben keinen Feedabruf":
    "Individual page links do not have a feed to refresh",
  "Dieser Endpunkt entfernt nur lokale Katalogeinträge":
    "This endpoint only removes local library entries",
  "Auswahl gehört nicht vollständig zu diesem Feed":
    "Some selected episodes do not belong to this feed",
  "MPD ist nicht erreichbar; Dateinutzung kann nicht geprüft werden":
    "MPD is unreachable; file usage cannot be checked",
  "Diese lokale Datei wird noch von MPD verwendet. Erst die Wiedergabequelle wechseln.":
    "MPD still uses this local file. Switch the playback source first.",
  "Audiodatei ist nicht verfügbar": "Audio file unavailable",
  "Auswahl enthält nicht bestätigte oder lokal verfügbare Episoden":
    "The selection includes unconfirmed or locally available episodes",
  "Auftrag nicht gefunden": "Job not found",
  "Ungültige Download-ID": "Invalid download ID",
  "Download nicht gefunden": "Download not found",
  "yt-dlp ist deaktiviert oder FFmpeg/yt-dlp fehlt":
    "yt-dlp is disabled or FFmpeg/yt-dlp is missing",
  "Diese Episode ist bereits eine lokale Datei":
    "This episode is already a local file",
  "Seitenlinks benötigen aktiviertes yt-dlp mit FFmpeg":
    "Page links require yt-dlp and FFmpeg",
  "Sammeldownload ist nur für RSS-Feeds verfügbar":
    "Bulk download is only available for RSS feeds",
  "Keine fertige lokale Kopie vorhanden": "No completed local copy available",
  "yt-dlp hat keine erkennbare Audiodatei erzeugt":
    "yt-dlp did not produce a recognized audio file",
  "Kein abbrechbarer Download vorhanden": "No cancellable download available",
  "Download ist noch nicht bereit": "Download is not ready yet",
  "Lokale Datei fehlt oder wurde geändert": "Local file missing or changed",
  "Die Quelle liefert keine Audiodatei":
    "The source did not return an audio file",
  "Datei überschreitet DOWNLOAD_MAX_BYTES": "File exceeds DOWNLOAD_MAX_BYTES",
  "Download ist leer oder unvollständig": "Download is empty or incomplete",
  "Download enthält keine erkennbare Audiodatei":
    "Download does not contain a recognized audio file",
  "Quelle nicht erreichbar oder Übertragung abgebrochen":
    "Source unreachable or transfer interrupted",
  "Feed nicht erreichbar oder ungültig": "Feed unreachable or invalid",
  "Auftrag wurde unterbrochen": "Job interrupted",
  "Verbindung zu MPD wird aufgebaut": "Connecting to MPD",
  "MPD konnte die aktuelle Episode nicht abspielen.":
    "MPD could not play the current episode.",
  "MPD nicht erreichbar oder Befehl fehlgeschlagen":
    "MPD unreachable or command failed",
  "YT-Import zuerst herunterladen": "Download the YT import first",
  "Keine direkte Audioquelle verfügbar": "No direct audio source available",
  "Audioquelle nicht erreichbar": "Audio source unreachable",
  "Audioquelle antwortet mit Fehler": "Audio source returned an error",
  "HTML statt Audio erhalten": "Received HTML instead of audio",
  "Genau position_seconds oder offset_seconds angeben":
    "Specify exactly one of position_seconds or offset_seconds",
  "YTDLP_JS_RUNTIME muss quickjs oder node sein":
    "YTDLP_JS_RUNTIME must be quickjs or node",
  "Bitte einen einzelnen Episoden-/Videolink statt einer Playlist oder eines Kanals angeben":
    "Enter a single episode or video link, not a playlist or channel",
  "Laufende Livestreams werden nicht heruntergeladen":
    "Live streams cannot be downloaded",
  "{count} Episode": "{count} episode",
  "{count} Episoden": "{count} episodes",
};
