# Node-RED and PlayPod API v1

The API controls the central MPD player. Browser playback has its own device-local queue and timer. Open `/docs` for all request/response models. Import [examples/node-red-playpod-v1.json](examples/node-red-playpod-v1.json), set the PlayPod base URL in its Function node, and deploy.

## Remote control with sleep defaults

HTTP Request node: **POST** `http://PLAYPOD-HOST:9393/api/v1/playback/toggle`, parsed JSON response. Function node before it:

```javascript
msg.headers = { "Content-Type": "application/json" };
msg.payload = { timer: "default", when_queue_empty: "default" };
return msg;
```

One request starts/resumes with the configured sleep duration (initially 15 minutes) and random selection, even if the UI previously disabled the timer. While already playing, Toggle pauses. Repeated Play while already playing does nothing. The same body is accepted by `playback/play` and `playback/next`.

### Timer and queue policy

| Field | Values |
| --- | --- |
| `timer` | `default`: select configured sleep duration; omitted/`keep`: retain selected duration and restart it on manual resume/Next; `preserve`: retain remaining time on Play/Toggle, used by the UI |
| `when_queue_empty` | omitted/`keep`: retain current policy; `default`: configured sleep choice; `stop`, `random`, `random_unheard`: explicit policy |

Pause does not consume time. Automatic episode transitions preserve the remaining timer; manual Next and explicit episode starts restart the selected duration. New manual title announcements do not consume the new timer period. A disabled timer stays disabled unless explicitly selected. `timer=default` alone does not select random continuation; send both default fields for the remote-control sleep use case.

`random_unheard` includes partially played episodes and excludes completed episodes. Both random policies start at 0:00; queued and explicitly selected episodes resume saved progress. No matching candidate means playback stops. Queue entries always take priority.

## Playback endpoints

All paths below are relative to `/api/v1`. JSON bodies are optional where shown as `{}`.

| Method and path | Body / behavior |
| --- | --- |
| GET `/state` | Full current MPD player state |
| POST `/playback/play` | Start/resume; optional timer/policy fields |
| POST `/playback/pause` | `{}`; pause |
| POST `/playback/toggle` | Toggle play/pause; optional timer/policy fields |
| POST `/playback/next` | Next queue/random episode; optional timer/policy fields |
| POST `/playback/undo` | `{}`; undo last unchanged skip |
| POST `/playback/sleep` | `{}`; activate configured sleep defaults and start/resume |
| POST `/playback/normal` | `{}`; pause and disable timer/random continuation |
| POST `/episodes/play` | `{"episode_id":42,"from_start":false}`; optional `timer` keep/default and policy |
| POST `/seek` | Exactly one: `{"position_seconds":120}` or `{"offset_seconds":-30}` |
| PUT `/volume` | `{"value":40}`; absolute 0–100 |
| POST `/volume/adjust` | `{"delta":5}` |
| PUT `/mode` | `{"favorites_only":true}` |
| POST `/mode/toggle` | `{}` |
| PUT `/timer` | `{"minutes":15}`; 0 disables, maximum 1440 |
| POST `/timer/extend` | `{"minutes":5}`; omitted body defaults to +5; requires enabled timer |
| POST `/queue` | `{"episode_id":42}` |
| PUT `/queue/order` | `{"ids":[42,43],"revision":3}` |
| DELETE `/queue` | Clear waiting entries; current episode keeps playing |
| DELETE `/queue/{episode_id}` | Remove entry |
| POST `/queue/{episode_id}/retry` | Retry failed queue entry |
| PUT `/config/sleep` | `{"minutes":15,"when_queue_empty":"random_unheard"}`; affects future activation |

Use explicit Play/Pause and absolute settings when retrying after unclear network delivery. Repeating Toggle, Next or relative adjustments can apply them twice. Without MPD configured, central controls return 503 `mpd_not_configured`; state/config remain readable.

## Catalog and jobs

Feed/episode management, bookmarks/completion, downloads, page links, local scans and manual URL checks are available under `/feeds`, `/episodes`, `/downloads`, `/links`, `/media`, `/cleanup` and `/jobs`. The interactive schema contains every endpoint and filter.

Feed refresh, media scan and URL checks return HTTP 202 with `job_id` and relative `status_url`. Download/link creation returns `id`, `episode_id`, `state`, `status_url`. Poll that URL to follow progress. Bulk feed downloads report `added`, `skipped`, `tasks`.

Deleting an imported collection's entries preserves the collection/favorite status and leaves audio files for orphan cleanup. Removing a local library entry never deletes its external file. Deleting a downloaded copy preserves the catalog episode and progress.

## State and errors

Successful player controls return HTTP 200 and the same model as GET `/state`:

- `state`: play/pause/stop/error; `current`: episode or null; `elapsed`, `duration`, `volume`.
- `phase`: episode/announcement; `announcement_kind`: title/mode/null; `announcement_text`.
- `timer`: enabled/minutes/remaining/run_active/suspended; `when_queue_empty`, `sleep_mode`.
- `queue`, `revision`, `undo_available`, `favorites_only`, `error`.

Failures use `{"error":{"code":"...","message":"...","details":[]}}`. Branch on `error.code`, not message text: 404 missing resources; 409 conflicts; 422 invalid input; 503 unavailable/unconfigured MPD; 500 internal error. Browser UI translates known messages without changing API error codes or stored state.

## Title announcements with Home Assistant/Piper

Set `TTS_AUDIO_URL` to a Node-RED endpoint. PlayPod sends the title as UTF-8 plain text; the flow calls Home Assistant POST `/api/tts_get_url` and returns JSON:

```json
{"url":"http://HOME-ASSISTANT:8123/api/tts_proxy/audio.wav"}
```

Set the voice in the Home Assistant call. The returned URL must be reachable by **MPD**, without a login redirect. The flow creates the file; it must not play it using `tts.speak` or `media_player.play_media`. PlayPod plays the announcement through MPD and starts the episode after MPD reports its end. Request/playback timeouts prevent a permanently blocked player.

Favorite-mode changes also use this audio-URL flow, including while paused/stopped. The previous source, position and play/pause state are restored afterwards; its timer is suspended during the mode announcement. Browser UI language does not change the central TTS voice or translate episode titles.

## MQTT and health

Optional retained status on `MQTT_TOPIC` (default `podplayer/status`): play, pause, stop, error. `/api/live` checks process liveness; `/api/health` checks SQLite and optional MPD. Actual Node-RED/Home Assistant deployment and audio output must be tested in your network.

## Text announcements (fire and forget)

Send one request; no follow-up request or callback is required:

```sh
curl -X POST http://PLAYPOD-HOST:9393/api/v1/announcements \
  -H 'Content-Type: application/json' \
  -d '{"text":"Die Waschmaschine ist fertig."}'
```

The endpoint returns **202 Accepted** immediately with the job `id`, `state: "queued"` and `queue_position`. This acknowledges durable acceptance, not completed playback. The worker uses the existing `TTS_AUDIO_URL` contract; Node-RED/Home Assistant TTS configuration stays the same. Text is required (1–2000 characters, trimmed); only `text` is accepted.

Announcements are played FIFO. PlayPod generates the first audio while the podcast continues, then pauses at the current position. Subsequent announcements play without restoring the podcast in between. The sleep timer stays frozen throughout the batch. When the queue is empty, the previous source and play/pause state are restored; a previously stopped output remains stopped. Failed messages are logged and skipped. Favorite-mode speech joins a running announcement batch. Queued text and the return context survive application restarts. Announcements do not create episode-completion activity.

An explicit episode change/Next or an external MPD source change during the announcement batch cancels its remaining messages. Playback remains under the user's control. Announcements use MPD; the independent browser player is unaffected.

For optional diagnostics: `GET /api/v1/announcements/ID` or `GET /api/v1/announcements`. States are `queued`, `generating`, `playing`, `done`, `failed`, `cancelled`; failures include `error`. The last 100 finished records are retained. Up to 50 active/pending messages are accepted; a full queue returns `429 announcement_queue_full`. Missing MPD/TTS configuration returns 503; invalid text returns 422. HTTP 202 does not require the caller to poll these endpoints.

## Activity API

`GET /api/v1/activity?kind=all|new|completed&limit=50&before=ID` returns `items` and `next_cursor` (null at the end). Each item contains its timestamp `created` (Unix seconds), kind (`episode_added`, `feed_added`, `completed`), snapshot titles, count, playback target and nullable episode/feed IDs. Only events from the last 90 days are retained. Use `next_cursor` as the next request's `before` value.

`GET /api/v1/activity/status?after=ID` returns `latest` and `unseen`. The UI stores the seen ID per browser; there is no shared read state. `GET /api/v1/episodes/ID/location` returns the feed ID and 50-item page offset for an exact management link (`#management/episodes/ID`). Initial imports link to `#management/feeds/ID`.

Browser progress optionally accepts `playback_id`, a stable identifier for one playback, to deduplicate completion retries. Existing progress clients and MPD/Node-RED playback commands remain compatible.

