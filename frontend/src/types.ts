export type Episode = {
  id: number;
  source_type: "audio" | "web";
  hidden?: number;
  feed_kind?: Feed["kind"];
  feed_id: number;
  title: string;
  podcast: string;
  url: string;
  cover: string;
  feed_cover: string;
  duration: number;
  position: number;
  last_started: number | null;
  completed: number;
  bookmarked: number;
  published: number | null;
  description: string;
  availability: string;
  check_error: string;
  queue_error?: string;
  local_source: string | null;
  media_root_id: number | null;
  source_present: number;
};
export type Feed = {
  id: number;
  url: string;
  title: string;
  favorite: number;
  cover: string;
  last_success: number | null;
  error: string;
  episode_count: number;
  kind: "rss" | "local" | "links" | "yt_playlist" | "yt_channel";
  import_status?: {
    found: number;
    eligible: number;
    excluded: number;
    unavailable: number;
    initial_limit_skipped: number;
    added: number;
    stored: number;
  } | null;
};
export type PlayerState = {
  phase: "announcement" | "episode";
  waiting_download?: boolean;
  announcement_kind?: "title" | "mode" | "custom" | null;
  announcement_text?: string;
  state: string;
  elapsed: number;
  duration: number;
  volume: number;
  current: Episode | null;
  queue: Episode[];
  revision: number;
  favorites_only: boolean;
  error: string;
  undo_available: boolean;
  when_queue_empty: "stop" | "random" | "random_unheard";
  sleep_mode: boolean;
  source_kind: "remote" | "local" | "announcement";
  timer: {
    enabled: boolean;
    minutes: number;
    remaining: number;
    run_active: boolean;
    suspended?: boolean;
  };
};
export type Config = {
  version: string;
  mpd: string;
  mpd_configured: boolean;
  mqtt: string;
  tts: string;
  tts_mode: "audio" | "disabled";
  database: string;
  rss_interval: number;
  rss_next_refresh?: number | null;
  rss_scheduler_running?: boolean;
  sleep_defaults: {
    minutes: number;
    when_queue_empty: "random" | "random_unheard";
  };
  rss_last_refresh: {
    created: number;
    finished: number | null;
    state: string;
    errors: number;
  } | null;
  media_base_url: string;
  media_roots: {
    id: number;
    root_key: string;
    path: string;
    enabled: number;
    online: boolean;
    read_only: boolean;
    episode_count: number;
    last_scan: number | null;
    error: string;
  }[];
};
export type Job = {
  id: string;
  kind: string;
  state: string;
  progress: number;
  total: number;
  error: string;
  results?: { id: number; status?: string; error?: string; ok?: boolean }[];
};
export type DialogState = {
  kind: "details" | "feed" | "confirm" | "cleanup" | "link";
  episode?: Episode;
  feed?: Feed;
  title?: string;
  body?: string;
  confirm?: () => Promise<void>;
};

export type Download = {
  title: string;
  podcast: string;
  in_use: boolean;
  phase: "download" | "processing";
  episode_id: number;
  id: string;
  state:
    | "queued"
    | "running"
    | "ready"
    | "error"
    | "cancelled"
    | "cancel_requested"
    | "missing"
    | "deleted";
  received: number;
  total: number | null;
  error: string;
};
export type DownloadStatus = {
  ytdlp_enabled: boolean;
  storage: {
    count: number;
    bytes: number;
    free_bytes: number;
    orphan_bytes: number;
  };
  enabled: boolean;
  online: boolean;
  error: string;
  items: Download[];
};
export type ActivityEvent = {
  id: number;
  kind: "episode_added" | "feed_added" | "completed";
  created: number;
  episode_id: number | null;
  feed_id: number | null;
  title: string;
  podcast: string;
  count: number;
  target: string;
};
export type ActivityPage = {
  items: ActivityEvent[];
  next_cursor: number | null;
};
