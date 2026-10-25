import { t, localeTag } from "./i18n.ts";
import type { Episode, PlayerState } from "./types";

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
type Source = {
  episode: Episode;
  url: string;
  source_kind: "remote" | "local";
};
const KEY = "playpod.browser.v1";
// randomUUID requires a secure context; getRandomValues also works on private HTTP hosts.
const newPlaybackId = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");

/** Device-local playback. No MPD state, queue or timer endpoints are called. */
export class BrowserPlayer {
  audio: HTMLAudioElement;
  request: Request;
  storage: Pick<Storage, "getItem" | "setItem">;
  changed: () => void;
  active = true;
  current: Episode | null = null;
  queue: Episode[] = [];
  revision = 0;
  favorites = false;
  seconds = 0;
  whenQueueEmpty: "stop" | "random" | "random_unheard" = "stop";
  sleepDefaults = {
    minutes: 15,
    when_queue_empty: "random_unheard" as "random" | "random_unheard",
  };
  left = 0;
  error = "";
  kind: "local" | "remote" = "remote";
  position = 0;
  prepared = false;
  pendingSeek = false;
  needsStarted = false;
  playbackId = "";
  generation = 0;
  advancing = false;
  lastTime = 0;
  lastReport = 0;
  progressChain = Promise.resolve();
  undo: { id: number; position: number; queue: Episode[] } | null = null;
  listeners: [string, EventListener][] = [];
  interval: ReturnType<typeof setInterval> | undefined;
  restored: {
    when_queue_empty?: "stop" | "random" | "random_unheard";
    current?: number;
    position?: number;
    queue?: number[];
    favorites?: boolean;
    seconds?: number;
    volume?: number;
    playback_id?: string;
  } = {};
  constructor(
    request: Request,
    changed: () => void,
    audio: HTMLAudioElement = new Audio(),
    storage?: Pick<Storage, "getItem" | "setItem">,
  ) {
    this.request = request;
    this.changed = changed;
    this.audio = audio;
    try {
      this.storage = storage ?? localStorage;
    } catch {
      this.storage = { getItem: () => null, setItem: () => {} };
    }
    audio.preload = "metadata";
    try {
      this.restored = JSON.parse(this.storage.getItem(KEY) || "{}") || {};
    } catch {}
    if (
      ["stop", "random", "random_unheard"].includes(
        this.restored.when_queue_empty || "",
      )
    )
      this.whenQueueEmpty = this.restored.when_queue_empty!;
    if (typeof this.restored.favorites === "boolean")
      this.favorites = this.restored.favorites;
    if (
      this.restored.when_queue_empty !== undefined &&
      Number.isFinite(this.restored.seconds) &&
      this.restored.seconds! >= 0 &&
      this.restored.seconds! <= 86400
    )
      this.seconds = this.restored.seconds!;
    this.left = this.seconds;
    audio.volume =
      typeof this.restored.volume === "number"
        ? Math.max(0, Math.min(1, this.restored.volume))
        : 0.55;
    this.listen("loadedmetadata", () => {
      if (!this.current) return;
      if (Number.isFinite(audio.duration))
        this.current.duration = audio.duration;
      if (this.pendingSeek) {
        try {
          audio.currentTime = this.position;
        } catch {}
        this.pendingSeek = false;
      }
      this.lastTime = audio.currentTime;
      this.changed();
    });
    this.listen("timeupdate", () => this.tick());
    this.listen("seeked", () => {
      this.lastTime = audio.currentTime;
      this.save();
      this.changed();
    });
    this.listen("playing", () => {
      if (!this.active) {
        audio.pause();
        return;
      }
      this.error = "";
      this.lastTime = audio.currentTime;
      this.changed();
    });
    this.listen("pause", () => {
      this.save();
      this.changed();
    });
    this.listen("ended", () => {
      if (!this.active || !this.current) return;
      if (this.seconds)
        this.left = Math.max(
          0,
          this.left - Math.max(0, audio.currentTime - this.lastTime),
        );
      this.lastTime = audio.currentTime;
      this.report(true);
      this.position = 0;
      if (this.seconds && this.left === 0) {
        this.changed();
        return;
      }
      void this.next(false).catch((e) => {
        this.error = (e as Error).message;
        this.changed();
      });
    });
    this.listen("error", () => {
      if (!this.current) return;
      this.error = t(
        "Audio kann im Browser nicht abgespielt werden. Quelle oder Format prüfen; gegebenenfalls herunterladen.",
      );
      this.changed();
    });
    this.interval = setInterval(() => this.tick(), 250);
    if (typeof navigator !== "undefined" && navigator.mediaSession) {
      for (const [name, path] of [
        ["play", "playback/play"],
        ["pause", "playback/pause"],
        ["nexttrack", "playback/next"],
      ] as const)
        try {
          navigator.mediaSession.setActionHandler(name, () => {
            if (!this.active) return;
            void this.command(path, "POST", { timer: "preserve" }).catch(
              () => {},
            );
          });
        } catch {}
    }
  }
  listen(name: string, handler: () => void) {
    this.audio.addEventListener(name, handler);
    this.listeners.push([name, handler]);
  }
  async init() {
    const get = async (id: number) => {
      try {
        return await this.request<Episode>("episodes/" + id);
      } catch {
        return null;
      }
    };
    if (Number.isInteger(this.restored.current)) {
      this.current = await get(this.restored.current!);
      this.position = Math.max(0, Number(this.restored.position) || 0);
      this.playbackId = this.restored.playback_id || "";
    }
    const ids = Array.isArray(this.restored.queue)
      ? [
          ...new Set(
            this.restored.queue.filter((id) => Number.isInteger(id) && id > 0),
          ),
        ].slice(0, 200)
      : [];
    this.queue = (await Promise.all(ids.map(get))).filter(
      (e): e is Episode => !!e,
    );
    this.changed();
  }
  save() {
    if (this.prepared && !this.pendingSeek)
      this.position = this.audio.currentTime;
    try {
      this.storage.setItem(
        KEY,
        JSON.stringify({
          current: this.current?.id,
          playback_id: this.playbackId,
          position: this.position,
          queue: this.queue.map((e) => e.id),
          favorites: this.favorites,
          seconds: this.seconds,
          when_queue_empty: this.whenQueueEmpty,
          volume: this.audio.volume,
        }),
      );
    } catch {}
  }
  snapshot(): PlayerState {
    return {
      state: this.current ? (this.audio.paused ? "pause" : "play") : "stop",
      phase: "episode",
      elapsed:
        this.prepared && !this.pendingSeek
          ? this.audio.currentTime
          : this.position,
      duration: this.current?.duration || 0,
      current: this.current,
      queue: this.queue,
      revision: this.revision,
      volume: Math.round(this.audio.volume * 100),
      favorites_only: this.favorites,
      error: this.error,
      undo_available: !!this.undo,
      when_queue_empty: this.whenQueueEmpty,
      sleep_mode: this.seconds > 0 && this.whenQueueEmpty !== "stop",
      source_kind: this.kind,
      timer: {
        enabled: this.seconds > 0,
        minutes: this.seconds / 60,
        remaining: this.left,
        run_active: !!this.current,
        suspended: false,
      },
    };
  }
  tick() {
    const time = this.audio.currentTime;
    if (
      !this.audio.paused &&
      !this.pendingSeek &&
      !this.audio.seeking &&
      this.seconds > 0
    ) {
      this.left = Math.max(0, this.left - Math.max(0, time - this.lastTime));
      if (this.left === 0) {
        this.audio.pause();
        this.report();
        this.save();
        this.changed();
      }
    }
    this.lastTime = time;
    if (
      this.prepared &&
      !this.audio.paused &&
      Date.now() - this.lastReport > 5000
    ) {
      this.report();
      this.save();
    }
  }
  report(completed = false, started = false) {
    if (!this.current) return;
    this.lastReport = Date.now();
    const data = {
      episode_id: this.current.id,
      position:
        this.prepared && !this.pendingSeek
          ? this.audio.currentTime
          : this.position,
      duration: this.current.duration || 0,
      completed,
      started,
      playback_id: this.playbackId || undefined,
    };
    this.progressChain = this.progressChain
      .catch(() => {})
      .then(() => this.request("browser/progress", "PUT", data))
      .then(() => {})
      .catch(() => {});
  }
  pause() {
    const playing = !this.audio.paused;
    this.generation++;
    this.tick();
    this.audio.pause();
    if (playing) this.report();
    this.save();
    this.changed();
  }
  async refreshCurrent() {
    if (!this.current) return;
    const id = this.current.id;
    try {
      const e = await this.request<Episode>("episodes/" + id);
      if (this.current?.id === id)
        this.current = {
          ...e,
          duration:
            this.prepared && Number.isFinite(this.audio.duration)
              ? this.audio.duration
              : e.duration,
        };
    } catch (e) {
      if (
        (e as Error & { status?: number }).status === 404 &&
        this.current?.id === id
      ) {
        this.pause();
        this.current = null;
        this.prepared = false;
        this.save();
      }
    }
  }
  async start(
    id: number,
    manual = true,
    fromStart = false,
    position?: number,
    playbackId?: string,
  ) {
    const gen = ++this.generation;
    const playing = !this.audio.paused;
    this.tick();
    if (playing) this.report();
    this.audio.pause();
    const source = await this.request<Source>(
      "browser/episodes/" + id + "/source",
    );
    if (gen !== this.generation) return false;
    this.current = source.episode;
    this.playbackId = playbackId || newPlaybackId();
    this.kind = source.source_kind;
    this.error = "";
    this.prepared = true;
    this.pendingSeek = true;
    this.needsStarted = true;
    this.position =
      position ??
      (fromStart || source.episode.completed ? 0 : source.episode.position);
    if (manual) this.left = this.seconds;
    this.audio.src = source.url;
    this.audio.load();
    this.lastTime = 0;
    if (this.audio.readyState >= 1) {
      this.audio.currentTime = this.position;
      this.lastTime = this.audio.currentTime;
      this.pendingSeek = false;
    }
    this.save();
    this.changed();
    try {
      await this.audio.play();
      if (gen !== this.generation) return false;
      this.confirmed();
      if (
        typeof navigator !== "undefined" &&
        navigator.mediaSession &&
        typeof MediaMetadata !== "undefined"
      )
        navigator.mediaSession.metadata = new MediaMetadata({
          title: this.current.title,
          artist: this.current.podcast,
        });
    } catch (e) {
      if (gen !== this.generation) return false;
      const blocked = (e as Error).name === "NotAllowedError";
      this.error = blocked
        ? t("Zum Starten der Browserwiedergabe bitte erneut Abspielen drücken.")
        : (e as Error).message || t("Audio konnte nicht gestartet werden");
      this.changed();
      throw e;
    }
    this.changed();
    return true;
  }
  async play(restartTimer = true) {
    if (!this.audio.paused) return;
    // An expired run has no remaining period to resume. A new run uses the preset.
    if (this.seconds > 0 && this.left <= 0) restartTimer = true;
    if (!this.current) {
      await this.next(restartTimer);
      return;
    }
    if (
      this.whenQueueEmpty !== "stop" &&
      (this.audio.ended ||
        (this.current.completed &&
          this.position >= this.current.duration &&
          this.current.duration > 0))
    ) {
      await this.next(restartTimer);
      return;
    }
    if (!this.prepared || this.audio.error) {
      await this.start(
        this.current.id,
        restartTimer,
        false,
        this.position,
        this.playbackId || undefined,
      );
      return;
    }
    if (this.audio.ended) {
      this.playbackId = newPlaybackId();
      this.audio.currentTime = 0;
      this.lastTime = 0;
      this.needsStarted = true;
    }
    if (restartTimer) this.left = this.seconds;
    this.error = "";
    const gen = ++this.generation;
    try {
      await this.audio.play();
      if (gen !== this.generation) return;
      this.lastTime = this.audio.currentTime;
      this.confirmed();
      this.save();
      this.changed();
    } catch (e) {
      if (gen !== this.generation) return;
      this.error = t("Browserwiedergabe benötigt einen Klick auf Abspielen.");
      this.changed();
      throw e;
    }
  }
  confirmed() {
    if (!this.current) return;
    if (this.queue.some((e) => e.id === this.current!.id)) {
      this.queue = this.queue.filter((e) => e.id !== this.current!.id);
      this.revision++;
    }
    if (this.needsStarted) {
      this.report(false, true);
      this.needsStarted = false;
    }
    this.save();
  }
  async next(manual = true) {
    if (this.advancing) return;
    this.advancing = true;
    const gen = this.generation;
    const old = this.current
      ? {
          id: this.current.id,
          position:
            this.prepared && !this.pendingSeek
              ? this.audio.currentTime
              : this.position,
          queue: [...this.queue],
        }
      : null;
    try {
      const candidates =
        this.whenQueueEmpty === "stop"
          ? []
          : await this.request<{ id: number }[]>(
              "browser/candidates?favorites_only=" +
                this.favorites +
                "&selection=" +
                this.whenQueueEmpty,
            );
      if (gen !== this.generation) return;
      const queued = this.queue.filter((e) => !e.queue_error).map((e) => e.id);
      const others = candidates
        .map((e) => e.id)
        .filter((id) => !queued.includes(id) && id !== this.current?.id);
      const ids = [...queued, ...others];
      if (!ids.length && !queued.length && candidates.length)
        ids.push(candidates[0].id);
      for (const id of ids.slice(0, 5)) {
        try {
          const started = await this.start(id, manual, !queued.includes(id));
          if (!started) return;
          this.undo = manual ? old : null;
          return;
        } catch (e) {
          if ((e as Error).name === "NotAllowedError") throw e;
          const entry = this.queue.find((e) => e.id === id);
          if (entry)
            entry.queue_error = t(
              "Episode konnte im Browser nicht gestartet werden",
            );
        }
      }
      if (manual && !ids.length)
        throw new Error(
          this.whenQueueEmpty === "stop"
            ? t("Warteschlange ist leer")
            : t("Keine passende Episode verfügbar"),
        );
      this.audio.pause();
      this.error = ids.length
        ? t("Keine weitere im Browser abspielbare Episode vorhanden")
        : "";
      this.changed();
    } finally {
      this.advancing = false;
      this.save();
    }
  }
  handles(path: string) {
    return /^(state$|playback\/|episodes\/play$|seek$|volume(?:\/adjust)?$|mode(?:\/toggle)?$|timer(?:\/extend)?$|queue(?:\/|$))/.test(
      path,
    );
  }
  async command(
    path: string,
    method = "GET",
    body: unknown = {},
  ): Promise<unknown> {
    const b = body as {
      timer?: "keep" | "default" | "preserve";
      episode_id: number;
      from_start: boolean;
      position_seconds?: number;
      offset_seconds?: number;
      value: number;
      delta: number;
      minutes: number;
      favorites_only: boolean;
      ids: number[];
      revision: number;
    };
    if (path === "state") return this.snapshot();
    if (path === "playback/sleep") {
      const before = {
        seconds: this.seconds,
        left: this.left,
        whenQueueEmpty: this.whenQueueEmpty,
      };
      this.seconds = this.sleepDefaults.minutes * 60;
      this.left = this.seconds;
      this.whenQueueEmpty = this.sleepDefaults.when_queue_empty;
      try {
        await this.play();
      } catch (e) {
        if ((e as Error).name !== "NotAllowedError")
          Object.assign(this, before);
        this.save();
        this.changed();
        throw e;
      }
      this.save();
      this.changed();
      return this.snapshot();
    }
    if (path === "playback/normal") {
      this.pause();
      this.seconds = this.left = 0;
      this.whenQueueEmpty = "stop";
      this.save();
      this.changed();
      return this.snapshot();
    }
    if (path === "episodes/play") {
      this.undo = null;
      await this.start(b.episode_id, true, b.from_start);
    } else if (path === "playback/next") await this.next();
    else if (path === "playback/undo") {
      if (!this.undo)
        throw new Error(t("Kein Überspringen zum Rückgängigmachen"));
      const old = this.undo;
      await this.start(old.id, true, false, old.position);
      this.queue = old.queue;
      this.undo = null;
      this.revision++;
    } else if (path === "playback/pause") this.pause();
    else if (path === "playback/play") await this.play(b.timer !== "preserve");
    else if (path === "playback/toggle") {
      if (this.audio.paused) await this.play(b.timer !== "preserve");
      else this.pause();
    } else if (path === "seek") {
      const value =
        b.position_seconds ??
        (this.prepared && !this.pendingSeek
          ? this.audio.currentTime
          : this.position) + (b.offset_seconds || 0);
      this.position = Math.max(
        0,
        Math.min(this.current?.duration || Infinity, value),
      );
      if (this.prepared) this.audio.currentTime = this.position;
      this.lastTime = this.position;
      this.report();
    } else if (path === "volume" || path === "volume/adjust")
      this.audio.volume = Math.max(
        0,
        Math.min(
          1,
          path === "volume" ? b.value / 100 : this.audio.volume + b.delta / 100,
        ),
      );
    else if (path === "timer") {
      this.seconds = b.minutes * 60;
      this.left = this.seconds;
    } else if (path === "timer/extend") {
      if (!this.seconds) throw new Error(t("Sleep-Timer ist ausgeschaltet"));
      this.left += (b.minutes || 5) * 60;
    } else if (path === "mode" || path === "mode/toggle")
      this.favorites = path === "mode" ? b.favorites_only : !this.favorites;
    else if (path === "queue" && method === "POST") {
      const added = !this.queue.some((e) => e.id === b.episode_id);
      if (added) {
        if (this.queue.length >= 200)
          throw new Error(t("Maximal 200 Einträge pro Browserqueue"));
        this.queue = [
          ...this.queue,
          await this.request<Episode>("episodes/" + b.episode_id),
        ];
        this.revision++;
        this.undo = null;
      }
      this.save();
      this.changed();
      return { added, state: this.snapshot() };
    } else if (path === "queue" && method === "DELETE") {
      this.queue = [];
      this.revision++;
      this.undo = null;
    } else if (path === "queue/order") {
      if (
        b.revision !== this.revision ||
        b.ids.length !== this.queue.length ||
        new Set(b.ids).size !== this.queue.length ||
        b.ids.some((id) => !this.queue.some((e) => e.id === id))
      )
        throw new Error(t("Warteschlange wurde geändert"));
      this.queue = b.ids.map((id) => this.queue.find((e) => e.id === id)!);
      this.revision++;
      this.undo = null;
    } else if (path.startsWith("queue/")) {
      const id = Number(path.split("/")[1]);
      if (path.endsWith("/retry")) {
        const e = this.queue.find((e) => e.id === id);
        if (e) e.queue_error = "";
      } else this.queue = this.queue.filter((e) => e.id !== id);
      this.revision++;
      this.undo = null;
    } else throw new Error(t("Browserbefehl nicht unterstützt"));
    this.save();
    this.changed();
    return this.snapshot();
  }
  dispose() {
    this.pause();
    clearInterval(this.interval);
    for (const [name, fn] of this.listeners)
      this.audio.removeEventListener(name, fn);
    this.audio.removeAttribute("src");
    this.audio.load();
  }
}
