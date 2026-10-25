import {
  t,
  localeTag,
  applyLanguage,
  setLanguage,
  getLanguagePreference,
  localizeMessage,
} from "./i18n";
import type {
  DownloadStatus,
  Episode,
  Feed,
  PlayerState,
  Config,
  Job,
  DialogState,
  ActivityEvent,
  ActivityPage,
} from "./types";
import { icon } from "./ui";
import { BrowserPlayer } from "./browser-player";
import { DisplayClock } from "./display-clock";
import { shortcut } from "./keyboard";
import { renderPlayer, queueItem, mini } from "./views/player";
import { renderManagement } from "./views/management";
import { renderActivity } from "./views/activity";
import { managementTarget } from "./activity";
import { renderConfig } from "./views/config";
import { renderDialog, feedForm, cleanupDialog } from "./views/dialogs";
import { LitElement, html, nothing, type PropertyValues } from "lit";
import { registerPwa } from "./pwa";
import "./styles.css";

export class PlayPodApp extends LitElement {
  static properties = {
    state: { state: true },
    target: { state: true },
    savingSleep: { state: true },
    downloads: { state: true },
    feeds: { state: true },
    episodes: { state: true },
    total: { state: true },
    managementLoaded: { state: true },
    view: { state: true },
    filter: { state: true },
    feedFilter: { state: true },
    query: { state: true },
    config: { state: true },
    jobs: { state: true },
    dialog: { state: true },
    job: { state: true },
    message: { state: true },
    connectionError: { state: true },
    busy: { state: true },
    seekDraft: { state: true },
    volumeDraft: { state: true },
    offset: { state: true },
    activityItems: { state: true },
    activityFilter: { state: true },
    activityCursor: { state: true },
    activityLoaded: { state: true },
    activityLoading: { state: true },
    activityError: { state: true },
    highlightedEpisode: { state: true },
    activityUnseen: { state: true },
  };
  state: PlayerState | null = null;
  target: "mpd" | "browser" | null = null;
  browser: BrowserPlayer | null = null;
  browserReady: Promise<void> | null = null;
  downloads: DownloadStatus = {
    enabled: false,
    ytdlp_enabled: false,
    storage: { count: 0, bytes: 0, free_bytes: 0, orphan_bytes: 0 },
    online: false,
    error: "",
    items: [],
  };
  feeds: Feed[] = [];
  episodes: Episode[] = [];
  total = 0;
  managementLoaded = false;
  view = "player";
  filter = "all";
  feedFilter: number | null = null;
  query = "";
  config: Config | null = null;
  jobs: Job[] = [];
  dialog: DialogState | null = null;
  job: Job | null = null;
  message = "";
  connectionError = "";
  busy = false;
  seekDraft: number | null = null;
  volumeDraft: number | null = null;
  offset = 0;
  activityItems: ActivityEvent[] = [];
  activityFilter = "all";
  activityCursor: number | null = null;
  activityLoaded = false;
  activityLoading = false;
  activityError = "";
  activitySequence = 0;
  highlightedEpisode: number | null = null;
  routeSequence = 0;
  activityUnseen = 0;
  activityLatest = 0;
  activitySeen = 0;
  displayClock = new DisplayClock();
  displayInterval?: number;
  commandStates = new WeakSet<object>();
  poll?: number;
  searchTimer?: number;
  messageTimer?: number;
  sequence = 0;
  refreshing = false;
  savingSleep = false;
  pendingCommands = 0;
  commandEpoch = 0;
  commandQueue: Promise<void> = Promise.resolve();
  dragId: number | null = null;
  createRenderRoot() {
    return this;
  }
  willUpdate(changed: PropertyValues) {
    if (changed.has("state") && this.state)
      this.displayClock.sync(
        this.state,
        performance.now(),
        this.commandStates.has(this.state),
      );
  }
  get announcementLabel() {
    return this.state?.announcement_kind === "mode"
      ? t("Modusansage")
      : this.state?.announcement_kind === "custom"
        ? t("Ansage")
        : t("Titelansage");
  }
  get nextLabel() {
    return this.state?.announcement_kind === "mode"
      ? t("Modusansage beenden und nächste Episode starten")
      : this.state?.announcement_kind === "custom"
        ? t("Ansage beenden und nächste Episode starten")
        : this.state?.phase === "announcement"
          ? t("Ansage überspringen und Episode starten")
          : this.state?.when_queue_empty === "stop"
            ? t("Nächste Episode aus der Warteschlange")
            : t("Nächste Episode: Warteschlange zuerst, sonst zufällig");
  }
  get canPlay() {
    return (
      !!this.state &&
      (this.state.phase === "announcement" ||
        !!this.state.current ||
        this.state.queue.length > 0 ||
        this.state.when_queue_empty !== "stop")
    );
  }
  get canNext() {
    return (
      !!this.state &&
      (this.state.phase === "announcement" ||
        this.state.queue.length > 0 ||
        this.state.when_queue_empty !== "stop")
    );
  }
  get displayElapsed() {
    return this.target === "browser" && this.browser
      ? this.browser.snapshot().elapsed
      : this.displayClock.read(performance.now()).elapsed;
  }
  get displayRemaining() {
    return this.target === "browser" && this.browser
      ? this.browser.left
      : this.displayClock.read(performance.now()).remaining;
  }
  connectedCallback() {
    super.connectedCallback();
    applyLanguage();
    this.readActivitySeen();
    window.addEventListener("playpod-language", this.onLanguage);
    window.addEventListener("languagechange", this.onSystemLanguage);
    registerPwa();
    this.view = this.route();
    void this.openManagementTarget();
    window.addEventListener("hashchange", this.onRoute);
    window.addEventListener("keydown", this.onKey);
    window.addEventListener("pagehide", this.onHide);
    void this.refresh();
    if (location.hash === "#config/sleep")
      void this.focusSection("sleep-config");
    if (location.hash === "#sleep")
      void this.updateComplete.then(() =>
        this.querySelector<HTMLButtonElement>('[data-action="sleep"]')?.focus(),
      );
    this.displayInterval = window.setInterval(() => this.requestUpdate(), 200);
    this.poll = window.setInterval(() => void this.refresh(), 2000);
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener("playpod-language", this.onLanguage);
    window.removeEventListener("languagechange", this.onSystemLanguage);
    this.browser?.dispose();
    window.removeEventListener("pagehide", this.onHide);
    window.clearInterval(this.poll);
    window.clearInterval(this.displayInterval);
    window.clearTimeout(this.searchTimer);
    window.clearTimeout(this.messageTimer);
    window.removeEventListener("hashchange", this.onRoute);
    window.removeEventListener("keydown", this.onKey);
  }
  onLanguage = () => {
    this.requestUpdate();
  };
  onSystemLanguage = () => {
    if (getLanguagePreference() === "auto") setLanguage("auto");
  };
  route() {
    return ["management", "activity", "config"].includes(
      location.hash.slice(1).split("/")[0],
    )
      ? location.hash.slice(1).split("/")[0]
      : "player";
  }
  onRoute = () => {
    this.view = this.route();
    this.offset = 0;
    this.highlightedEpisode = null;
    void this.openManagementTarget();
    if (!managementTarget(location.hash)) void this.loadManagement();
    if (this.view === "activity") void this.loadActivity();
    window.scrollTo({ top: 0 });
    if (location.hash === "#config/sleep")
      void this.focusSection("sleep-config");
    if (location.hash === "#sleep")
      void this.updateComplete.then(() =>
        this.querySelector<HTMLButtonElement>('[data-action="sleep"]')?.focus(),
      );
  };
  onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape" && !this.dialog) {
      const menus =
        this.querySelectorAll<HTMLDetailsElement>(".action-menu[open]");
      if (menus.length) {
        e.preventDefault();
        menus.forEach((menu) => {
          menu.open = false;
          menu.querySelector<HTMLElement>("summary")?.focus();
        });
        return;
      }
    }
    const target = e.target instanceof Element ? e.target : null;
    const action = shortcut(
      e,
      !!target?.closest(
        "input,textarea,select,[contenteditable]:not([contenteditable=false]),[role=textbox]",
      ),
      !!target?.closest("button,a,summary,[role=button]"),
      !!this.dialog,
    );
    if (action === "player") {
      e.preventDefault();
      this.view = "player";
      this.navigate("player");
      void this.updateComplete.then(() =>
        this.querySelector<HTMLElement>("main h1")?.focus(),
      );
      return;
    }
    if (action) {
      e.preventDefault();
      // Holding a volume key must not build up seconds of delayed commands.
      if (e.repeat && this.pendingCommands >= 2) return;
      void this.perform(() => this.action(action), true);
    }
  };
  onHide = () => {
    if (this.target === "browser") this.browser?.pause();
  };
  async ensureBrowser() {
    if (!this.browser) {
      this.browser = new BrowserPlayer(
        (path, method, body) => this.rawApi(path, method, body),
        () => {
          if (this.target === "browser" && this.browser)
            this.state = this.browser.snapshot();
        },
      );
      this.browserReady = this.browser.init();
    }
    await this.browserReady;
  }
  async selectTarget(target: "mpd" | "browser") {
    if (target === "mpd" && !this.config?.mpd_configured) return;
    if (this.target === "browser") this.browser?.pause();
    if (target === "browser") await this.ensureBrowser();
    this.target = target;
    if (this.browser) {
      this.browser.active = target === "browser";
      this.browser.report();
    }
    try {
      localStorage.setItem("playpod.target", target);
    } catch {}
    this.state =
      target === "browser"
        ? this.browser!.snapshot()
        : await this.rawApi<PlayerState>("state");
    this.seekDraft = this.volumeDraft = null;
  }
  async api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
    if (this.target === "browser" && this.browser?.handles(path)) {
      const result = await this.browser.command(path, method, body);
      if (method !== "GET" && result && typeof result === "object")
        this.commandStates.add(result);
      return result as T;
    }
    return this.rawApi(path, method, body);
  }
  async rawApi<T>(path: string, method = "GET", body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    try {
      const r = await fetch("/api/v1/" + path, {
        method,
        keepalive: path === "browser/progress",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      if (!r.ok) {
        let detail = t("Anfrage fehlgeschlagen");
        try {
          const d = await r.json();
          if (typeof d.error?.message === "string") detail = d.error.message;
        } catch {}
        throw Object.assign(new Error(detail), { status: r.status });
      }
      const result = await r.json();
      if (method !== "GET" && result && typeof result === "object")
        this.commandStates.add(result);
      return result as T;
    } finally {
      clearTimeout(timeout);
    }
  }
  notify(text: string) {
    this.message = localizeMessage(text);
    clearTimeout(this.messageTimer);
    this.messageTimer = window.setTimeout(() => (this.message = ""), 4500);
  }
  async refresh() {
    if (this.refreshing || this.pendingCommands) return;
    this.refreshing = true;
    const epoch = this.commandEpoch;
    try {
      const [state, config, jobs, downloads] = await Promise.all([
        this.api<PlayerState>("state"),
        this.api<Config>("config"),
        this.api<Job[]>("jobs"),
        this.api<DownloadStatus>("downloads"),
      ]);
      if (epoch !== this.commandEpoch) return;
      this.config = config;
      if (this.target === null) {
        let saved = "";
        try {
          saved = localStorage.getItem("playpod.target") || "";
        } catch {}
        this.target =
          !config.mpd_configured || saved === "browser" ? "browser" : "mpd";
      }
      if (!config.mpd_configured && this.target === "mpd")
        this.target = "browser";
      if (this.target === "browser") {
        await this.ensureBrowser();
        this.browser!.sleepDefaults = config.sleep_defaults;
        await this.browser!.refreshCurrent();
        if (epoch !== this.commandEpoch) return;
        this.state = this.browser!.snapshot();
      } else this.state = state;
      this.jobs = jobs;
      this.downloads = downloads;
      this.connectionError = "";
      if (this.view === "management") await this.loadManagement();
      await this.loadActivityStatus();
      if (this.view === "activity") await this.loadActivity();
      if (this.dialog?.kind === "cleanup" && this.job)
        this.job = await this.api<Job>("jobs/" + this.job.id);
    } catch {
      if (epoch === this.commandEpoch)
        this.connectionError = t(
          "Verbindung zu PlayPod unterbrochen. Status wird erneut abgefragt.",
        );
    } finally {
      this.refreshing = false;
    }
  }
  async loadManagement() {
    if (this.view !== "management") return;
    const seq = ++this.sequence;
    const args = new URLSearchParams({
      q: this.query,
      filter: this.filter,
      offset: String(this.offset),
      limit: "50",
    });
    if (this.feedFilter) args.set("feed_id", String(this.feedFilter));
    try {
      const [feeds, result] = await Promise.all([
        this.api<Feed[]>("feeds?" + new URLSearchParams({ q: this.query })),
        this.api<{ items: Episode[]; total: number }>("episodes?" + args),
      ]);
      if (seq === this.sequence) {
        this.feeds = feeds;
        this.episodes = result.items;
        this.total = result.total;
        this.managementLoaded = true;
      }
    } catch (e) {
      this.notify((e as Error).message);
    }
  }
  setActivityFilter(value: string) {
    this.activitySequence++;
    this.activityFilter = value;
    this.activityItems = [];
    this.activityCursor = null;
    this.activityLoaded = false;
    this.activityLoading = false;
    void this.loadActivity();
  }
  readActivitySeen() {
    try {
      const saved = Number(localStorage.getItem("playpod.activity.seen"));
      if (Number.isSafeInteger(saved) && saved >= 0) this.activitySeen = saved;
    } catch {}
  }
  async loadActivityStatus() {
    try {
      this.readActivitySeen();
      const status = await this.rawApi<{ latest: number; unseen: number }>(
        `activity/status?after=${this.activitySeen}`,
      );
      this.activityLatest = status.latest;
      this.activityUnseen = status.unseen;
    } catch {
      /* Activity availability must not disrupt playback. */
    }
  }
  markActivitySeen() {
    if (this.view !== "activity" || document.visibilityState !== "visible")
      return;
    this.activitySeen = Math.max(
      this.activitySeen,
      this.activityLatest,
      ...this.activityItems.map((event) => event.id),
    );
    this.activityUnseen = 0;
    try {
      localStorage.setItem("playpod.activity.seen", String(this.activitySeen));
    } catch {}
  }
  async loadActivity(more = false) {
    if (this.view !== "activity" || this.activityLoading) return;
    const seq = ++this.activitySequence;
    this.activityLoading = true;
    const args = new URLSearchParams({ kind: this.activityFilter });
    if (more && this.activityCursor)
      args.set("before", String(this.activityCursor));
    try {
      const page = await this.rawApi<ActivityPage>("activity?" + args);
      if (seq !== this.activitySequence) return;
      const overlaps = page.items.some((event) =>
        this.activityItems.some((old) => old.id === event.id),
      );
      const old =
        more || (overlaps && this.activityItems.length > 50)
          ? this.activityItems
          : [];
      const merged = new Map(
        [...old, ...page.items].map((event) => [event.id, event]),
      );
      this.activityItems = [...merged.values()]
        .filter((event) => event.created >= Date.now() / 1000 - 90 * 86400)
        .sort((a, b) => b.id - a.id);
      if (more || !old.length) this.activityCursor = page.next_cursor;
      this.activityLoaded = true;
      this.activityError = "";
      this.markActivitySeen();
    } catch (error) {
      if (seq === this.activitySequence) {
        this.activityError = (error as Error).message;
        this.activityLoaded = true;
      }
    } finally {
      if (seq === this.activitySequence) this.activityLoading = false;
    }
  }
  async openManagementTarget() {
    const seq = ++this.routeSequence;
    const target = managementTarget(location.hash);
    if (!target) return;
    // Invalidate any outgoing list request before resolving the target page.
    this.sequence++;
    try {
      const locationInfo =
        target.kind === "episodes"
          ? await this.rawApi<{ feed_id: number; offset: number }>(
              `episodes/${target.id}/location`,
            )
          : { feed_id: target.id, offset: 0 };
      if (seq !== this.routeSequence || this.view !== "management") return;
      this.query = "";
      this.filter = "all";
      this.feedFilter = locationInfo.feed_id;
      this.offset = locationInfo.offset;
      this.highlightedEpisode = target.kind === "episodes" ? target.id : null;
      await this.loadManagement();
      if (seq !== this.routeSequence) return;
      await this.focusSection(
        this.highlightedEpisode
          ? `episode-${this.highlightedEpisode}`
          : "episode-list",
      );
    } catch (error) {
      if (seq !== this.routeSequence) return;
      this.query = "";
      this.filter = "all";
      this.feedFilter = null;
      await this.loadManagement();
      this.notify((error as Error).message);
    }
  }
  perform(fn: () => Promise<unknown>, quiet = false): Promise<void> {
    this.pendingCommands++;
    this.commandEpoch++;
    const run = async () => {
      this.busy = !quiet;
      try {
        await fn();
      } catch (e) {
        this.notify((e as Error).message);
      } finally {
        this.busy = false;
        this.pendingCommands--;
        if (!this.pendingCommands) await this.refresh();
      }
    };
    this.commandQueue = this.commandQueue.then(run);
    return this.commandQueue;
  }
  navigate(view: string) {
    location.hash = view;
  }
  async focusSection(id: string) {
    await this.updateComplete;
    const section = this.querySelector<HTMLElement>("#" + id);
    section?.scrollIntoView({ block: "start", behavior: "instant" });
    section?.focus({ preventScroll: true });
  }
  async selectFeed(id: number) {
    this.feedFilter = id;
    this.offset = 0;
    await this.loadManagement();
    await this.focusSection("episode-list");
  }
  async open(d: DialogState) {
    this.dialog = d;
    await this.updateComplete;
    this.querySelector("dialog")?.showModal();
  }
  close() {
    this.querySelector("dialog")?.close();
    this.dialog = null;
    this.job = null;
  }
  confirm(title: string, body: string, confirm: () => Promise<void>) {
    void this.open({ kind: "confirm", title, body, confirm });
  }
  cover(ep: Episode | Feed | null, big = false) {
    let cover = ep
      ? "feed_cover" in ep
        ? ep.cover || ep.feed_cover
        : ep.cover
      : "";
    if (cover && !/^https?:\/\//i.test(cover)) cover = "";
    const text = ep ? ("podcast" in ep ? ep.podcast : ep.title) : "PLAYPOD";
    const color = ["sage", "rust", "blue", "violet"][(ep?.id || 0) % 4];
    return html`<div
      class="art ${big ? "big" : "mini"} ${color}"
      aria-hidden="true"
    >
      <strong
        >${text
          .split(/\s+/)
          .filter(Boolean)
          .slice(0, 2)
          .map((word) => word[0].toLocaleUpperCase())
          .join("")}</strong
      >${cover ? html`<img src=${cover} alt="" loading="lazy" @error=${(e: Event) => (e.currentTarget as HTMLImageElement).remove()} />` : nothing}
    </div>`;
  }
  async action(action: string, id?: number) {
    const state = this.state;
    if (!state) return;
    switch (action) {
      case "volume-up":
      case "volume-down": {
        this.state = await this.api("volume/adjust", "POST", {
          delta: action === "volume-up" ? 5 : -5,
        });
        break;
      }
      case "sleep":
        this.state = await this.api(
          this.state?.sleep_mode ? "playback/toggle" : "playback/sleep",
          "POST",
          this.state?.sleep_mode ? { timer: "preserve" } : {},
        );
        break;
      case "normal":
        this.state = await this.api("playback/normal", "POST");
        break;
      case "toggle":
        this.state = await this.api("playback/toggle", "POST", {
          timer: "preserve",
        });
        break;
      case "next":
      case "undo":
        this.state = await this.api("playback/" + action, "POST");
        break;
      case "rewind":
      case "forward":
        this.state = await this.api("seek", "POST", {
          offset_seconds: action === "forward" ? 30 : -30,
        });
        break;
      case "mode":
        this.state = await this.api("mode/toggle", "POST");
        break;
      case "extend":
        this.state = await this.api("timer/extend", "POST", { minutes: 5 });
        break;
      case "play":
        this.state = await this.api("episodes/play", "POST", {
          episode_id: id,
        });
        this.notify(
          this.state?.phase === "announcement"
            ? t("Titelansage gestartet.")
            : t("Wiedergabe gestartet."),
        );
        break;
      case "enqueue": {
        const r = await this.api<{ added: boolean; state: PlayerState }>(
          "queue",
          "POST",
          { episode_id: id },
        );
        this.state = r.state;
        this.notify(
          r.added
            ? t("An Warteschlange angehängt.")
            : t("Bereits in der Warteschlange."),
        );
        break;
      }
      case "download":
        await this.api(`episodes/${id}/download`, "POST");
        this.notify(t("Download vorgemerkt."));
        break;
      case "download-cancel":
        await this.api(`episodes/${id}/download`, "DELETE");
        this.notify(t("Download wird abgebrochen."));
        break;
      case "bookmark": {
        const ep =
          state.current?.id === id
            ? state.current
            : this.episodes.find((e) => e.id === id);
        if (ep) {
          await this.api(`episodes/${id}/bookmark`, "PUT", {
            value: !ep.bookmarked,
          });
          this.notify(
            ep.bookmarked ? t("Merker entfernt.") : t("Für später gemerkt."),
          );
        }
        break;
      }
      case "queue-remove":
        this.state = await this.api("queue/" + id, "DELETE");
        break;
      case "retry":
        this.state = await this.api("queue/" + id + "/retry", "POST");
        break;
      case "up":
      case "down":
      case "first": {
        const ids = state.queue.map((e) => e.id),
          index = ids.indexOf(id!);
        if (index < 0) return;
        const target =
          action === "first" ? 0 : index + (action === "up" ? -1 : 1);
        if (target < 0 || target >= ids.length) return;
        ids.splice(index, 1);
        ids.splice(target, 0, id!);
        await this.order(ids);
        break;
      }
      case "details": {
        const ep = await this.api<Episode>("episodes/" + id);
        await this.open({ kind: "details", episode: ep });
        break;
      }
      case "favorite": {
        const f = this.feeds.find((f) => f.id === id);
        if (f)
          await this.api("feeds/" + id, "PUT", {
            url: f.url,
            title: f.title,
            favorite: !f.favorite,
          });
        break;
      }
      case "refresh": {
        const job = await this.api<{ job_id: string }>(
          id ? "feeds/" + id + "/refresh" : "feeds/refresh",
          "POST",
        );
        this.notify(
          this.feeds.find((f) => f.id === id)?.kind === "local"
            ? t("Lokaler Verzeichnisscan gestartet.")
            : t("Feedaktualisierung gestartet."),
        );
        void job;
        break;
      }
      case "scan-media":
        await this.api("media/scan", "POST");
        this.notify(t("Lokale Verzeichnisse werden eingelesen."));
        break;
    }
  }
  async order(ids: number[]) {
    if (this.state)
      this.state = await this.api("queue/order", "PUT", {
        ids,
        revision: this.state.revision,
      });
  }
  onAction = (e: Event) => {
    if (
      e.target instanceof HTMLDetailsElement &&
      e.target.classList.contains("action-menu")
    )
      e.target.open = false;
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>(
      "button[data-action]",
    );
    this.querySelectorAll<HTMLDetailsElement>(".action-menu[open]").forEach(
      (menu) => {
        if (!menu.contains(e.target as Node)) menu.open = false;
      },
    );
    if (!b || b.disabled) return;
    b.closest(".action-menu")?.removeAttribute("open");
    const action = b.dataset.action!,
      id = Number(b.dataset.id) || undefined;
    if (action === "link-add") {
      void this.open({ kind: "link" });
      return;
    }
    if (action === "download-delete") {
      const d = this.downloads.items.find((d) => d.episode_id === id);
      this.confirm(
        t("Lokale Kopie löschen?"),
        t(
          "Die Audiodatei von „{title}“ wird gelöscht. Episode, Merker und Hörfortschritt bleiben erhalten.",
          { title: d?.title || t("Episode") },
        ) +
          " " +
          (this.episodes.find((e) => e.id === id)?.source_type === "web"
            ? t(
                "Zum erneuten Abspielen muss der Seitenlink wieder heruntergeladen werden.",
              )
            : t("Feedepisoden werden anschließend wieder gestreamt.")),
        async () => {
          await this.api(`episodes/${id}/download/file`, "DELETE");
          this.close();
          this.notify(t("Lokale Kopie gelöscht."));
        },
      );
      return;
    }
    if (action === "downloads-cleanup") {
      this.confirm(
        t("Verwaiste Downloads löschen?"),
        t(
          "Es werden nur nicht mehr zugeordnete Dateien im PlayPod-Downloadordner entfernt. Externe Medienverzeichnisse bleiben unverändert.",
        ),
        async () => {
          await this.api("downloads/cleanup", "POST");
          this.close();
        },
      );
      return;
    }
    if (action === "feed-delete-heard") {
      void this.perform(async () => {
        const preview = await this.api<{ count: number }>(
          `feeds/${id}/downloads/completed`,
        );
        if (!preview.count) {
          this.notify(t("Keine gehörten Downloads vorhanden."));
          return;
        }
        this.confirm(
          t("Gehörte Downloads löschen?"),
          t(
            "{count} lokale Kopien löschen? Episoden, Merker und Hörfortschritt bleiben erhalten. Verwendete Dateien werden ausgelassen.",
            { count: preview.count },
          ),
          async () => {
            const result = await this.api<{
              deleted: number;
              skipped: number;
              failed: number;
            }>(`feeds/${id}/downloads/completed`, "DELETE");
            this.close();
            this.notify(
              t(
                "{deleted} Kopien gelöscht · {skipped} verwendet · {failed} fehlgeschlagen",
                result,
              ),
            );
          },
        );
      });
      return;
    }
    if (action === "feed-download") {
      void this.perform(async () => {
        const preview = await this.api<{ count: number; ids: number[] }>(
          `feeds/${id}/downloads/preview`,
        );
        if (!preview.count) {
          this.notify(t("Keine ungehörten Episoden ohne Download vorhanden."));
          return;
        }
        this.confirm(
          t("Feedepisoden herunterladen?"),
          t(
            "{count} ungehörte Episoden werden nacheinander heruntergeladen. Bereits geladene oder vorgemerkte Folgen werden übersprungen. Die Gesamtgröße ist vorher nicht bekannt.",
            { count: preview.ids.length },
          ) +
            (preview.count > preview.ids.length
              ? t(" Pro Start werden höchstens 1000 Episoden vorgemerkt.")
              : ""),
          async () => {
            const r = await this.api<{ added: number }>(
              `feeds/${id}/downloads`,
              "POST",
              { ids: preview.ids },
            );
            this.close();
            this.notify(t("{count} Downloads vorgemerkt.", { count: r.added }));
          },
        );
      });
      return;
    }
    if (action === "clear") {
      this.confirm(
        t("Warteschlange leeren?"),
        t(
          "Die wartenden Einträge werden entfernt. Die aktuelle Wiedergabe läuft weiter.",
        ),
        async () => {
          this.state = await this.api("queue", "DELETE");
          this.close();
        },
      );
      return;
    }
    if (action === "feed-add" || action === "feed-edit") {
      void this.open({
        kind: "feed",
        feed: this.feeds.find((f) => f.id === id),
      });
      return;
    }
    if (action === "link-clear") {
      const f = this.feeds.find((f) => f.id === id);
      if (f)
        this.confirm(
          t("Importliste leeren?"),
          t(
            "Alle Einträge aus „{title}“ samt Merkern, Hörfortschritt und Warteschlangeneinträgen entfernen? Eine zugehörige Wiedergabe stoppt. Die Sammlung und ihr Favoritenstatus bleiben erhalten. Audiodateien bleiben auf dem Datenträger und können unter Einstellungen als verwaiste Dateien aufgeräumt werden.",
            { title: f.title },
          ),
          async () => {
            await this.api("feeds/" + id + "/episodes", "DELETE");
            this.close();
          },
        );
      return;
    }
    if (action === "feed-delete") {
      const f = this.feeds.find((f) => f.id === id);
      if (f)
        this.confirm(
          t("Podcast endgültig löschen?"),
          t(
            "„{title}“ samt Episoden, Merkern und Warteschlangeneinträgen löschen? Eine zugehörige Wiedergabe stoppt. Heruntergeladene Audiodateien bleiben bis zum Aufräumen verwaister Dateien erhalten.",
            { title: f.title },
          ),
          async () => {
            await this.api("feeds/" + id, "DELETE");
            if (this.feedFilter === id) this.feedFilter = null;
            this.close();
          },
        );
      return;
    }
    if (action === "remove-local") {
      this.confirm(
        t("Aus Katalog entfernen?"),
        t(
          "Die Audiodatei bleibt unverändert auf dem Datenträger. Ein erneuter Scan nimmt sie wieder auf. Merker und Fortschritt dieses Eintrags werden entfernt; eine zugehörige Wiedergabe stoppt.",
        ),
        async () => {
          await this.api("episodes/" + id, "DELETE");
          this.close();
        },
      );
      return;
    }
    if (action === "cleanup") {
      this.job = null;
      void this.open({ kind: "cleanup" });
      return;
    }
    if (action === "close") {
      this.close();
      return;
    }
    void this.perform(
      () => this.action(action, id),
      [
        "toggle",
        "sleep",
        "normal",
        "next",
        "undo",
        "rewind",
        "forward",
        "mode",
        "extend",
        "play",
        "bookmark",
      ].includes(action),
    );
  };
  button(
    action: string,
    label: string,
    iconName: string,
    id?: number,
    disabled = false,
  ) {
    return html`<button
      class="icon ghost"
      data-action=${action}
      data-id=${id || ""}
      aria-label=${label}
      title=${label}
      ?disabled=${disabled || this.busy}
    >
      ${icon(iconName)}
    </button>`;
  }
  nav(mobile = false) {
    return html`<nav
      class=${mobile ? "mobile-nav" : ""}
      aria-label=${mobile ? t("Hauptnavigation mobil") : t("Hauptnavigation")}
    >
      ${[
        ["player", t("Player"), "player"],
        ["management", t("Bibliothek"), "library"],
        ["activity", t("Aktivität"), "activity"],
        ["config", t("Einstellungen"), "config"],
      ].map(
        ([v, label, i]) =>
          html`<button
            class=${v === this.view ? "active" : ""}
            aria-current=${v === this.view ? "page" : nothing}
            aria-keyshortcuts=${v === "player" ? "P" : nothing}
            @click=${() => this.navigate(v)}
          >
            ${icon(i)}<span
              >${label}${v === "activity" && this.activityUnseen > 0 ? html`<span class="nav-count" aria-label=${t("{count} ungesehene Ereignisse", { count: this.activityUnseen })}>${this.activityUnseen > 99 ? "99+" : this.activityUnseen}</span>` : nothing}</span
            >
          </button>`,
      )}
    </nav>`;
  }
  render() {
    const state = this.state;
    return html`<div @click=${this.onAction}>
      <aside class="sidebar">
        <div class="brand">
          <a
            class="brand-mark"
            href="https://github.com/desirevolution/playpod"
            target="_blank"
            rel="noopener noreferrer"
            aria-label=${t("PlayPod auf GitHub öffnen (neuer Tab)")}
            title=${t("PlayPod auf GitHub öffnen (neuer Tab)")}
            >${icon("logo")}</a
          >PlayPod
        </div>
        ${this.nav()}
        <div class="sidebar-bottom">
          <p class="muted small">
            ${this.config?.version || t("Verbindung wird aufgebaut")}
          </p>
        </div>
      </aside>
      <main>
        <header class="top">
          <div>
            <h1 tabindex="-1">
              ${{ player: t("Player"), management: t("Bibliothek"), activity: t("Aktivität"), config: t("Einstellungen") }[this.view]}
            </h1>
          </div>
          <div class="playback-target">
            <span class="badge playback-status"
              >${state?.phase === "announcement" ? (state.state === "pause" ? this.announcementLabel + t(" pausiert") : this.announcementLabel + t(" läuft")) : state?.state === "play" ? t("Wiedergabe läuft") : state?.state === "pause" ? t("Pausiert") : t("Gestoppt")}</span
            >
            ${
              this.config?.mpd_configured
                ? html`<div class="target-control">
                    <button
                      type="button"
                      class="target-switch"
                      ?disabled=${this.pendingCommands > 0}
                      role="switch"
                      aria-labelledby="target-label"
                      aria-checked=${this.target === "browser"}
                      @click=${() => void this.perform(() => this.selectTarget(this.target === "browser" ? "mpd" : "browser"), true)}
                    >
                      <span class="switch-track" aria-hidden="true"
                        ><span></span
                      ></span>
                      <span id="target-label"
                        >${t("In diesem Browser abspielen")}</span
                      >
                    </button>
                  </div>`
                : html`<span class="badge">${t("Dieser Browser")}</span>`
            }
            ${this.config?.mpd_configured ? html`<span class="target-hint">${this.target === "browser" ? t("Eigene Queue · MPD läuft unabhängig") : "MPD"}</span>` : nothing}
          </div>
        </header>
        ${this.connectionError ? html`<div class="error-banner" role="alert">${localizeMessage(this.connectionError)}</div>` : nothing}${state?.error ? html`<div class="error-banner" role="alert">${localizeMessage(state.error)}</div>` : nothing}${this.view === "player" ? this.renderPlayer() : this.view === "management" ? this.renderManagement() : this.view === "activity" ? renderActivity.call(this) : this.renderConfig()}
      </main>
      ${this.view !== "player" && state?.current ? this.mini() : nothing}${this.nav(true)}${this.message ? html`<div class="toast" role="status">${localizeMessage(this.message)}</div>` : nothing}${this.renderDialog()}
    </div>`;
  }
  renderPlayer() {
    return renderPlayer.call(this);
  }
  queueItem(e: Episode, i: number) {
    return queueItem.call(this, e, i);
  }
  mini() {
    return mini.call(this);
  }
  renderManagement() {
    return renderManagement.call(this);
  }
  renderConfig() {
    return renderConfig.call(this);
  }
  renderDialog() {
    return renderDialog.call(this);
  }
  feedForm(feed?: Feed) {
    return feedForm.call(this, feed);
  }
  cleanupDialog() {
    return cleanupDialog.call(this);
  }
}
customElements.define("playpod-app", PlayPodApp);
