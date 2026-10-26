import { t, localeTag, localizeMessage, countText } from "../i18n";
import { html, nothing } from "lit";
import { live } from "lit/directives/live.js";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import type { PlayPodApp } from "../main";
import type { Episode, Feed, Job } from "../types";
import { fmt, date, icon } from "../ui";
import { downloadInfo } from "./management";
export function renderPlayer(this: PlayPodApp) {
  const s = this.state,
    e = s?.current;
  const timerPresets = [0, 15, 30, 45, 60];
  if (s && !timerPresets.includes(s.timer.minutes)) {
    timerPresets.push(s.timer.minutes);
    timerPresets.sort((a, b) => a - b);
  }
  return html`<section aria-label=${t("Player")}>
    <div class="player-grid">
      <article class="panel player-main ${e ? "" : "is-empty"}">
        ${playbackTarget.call(this)}
        ${s?.waiting_download ? html`<p class="notice" role="status">${t("Download wird vorbereitet. Wiedergabe und Sleep-Timer warten.")}</p>` : nothing}
        ${s?.announcement_kind === "custom" ? html`<p class="notice" role="status">${t("Ansage")}: ${s.announcement_text}</p>` : nothing}
        <div class="player-hero ${e ? "" : "is-empty"}">
          ${e ? this.cover(e, true) : html`<div class="empty-player-art" aria-hidden="true">${icon("speaker")}</div>`}
          <div class="player-body">
            <div class="playing-meta">
              <p class="eyebrow">
                ${e?.podcast || t("Keine Episode ausgewählt")}
              </p>
              <h2>
                ${e?.title || (s?.announcement_kind === "mode" || s?.announcement_kind === "custom" ? s.announcement_text : t("Bereit zum Abspielen"))}
              </h2>
              ${
                e
                  ? html`<button
                      class="description"
                      data-action="details"
                      data-id=${e.id}
                    >
                      ${t("Beschreibung ansehen ↗")}
                    </button>`
                  : html`<p class="muted empty-player-hint">
                        ${s && s.when_queue_empty !== "stop" ? t("Play startet die Warteschlange oder eine passende zufällige Episode.") : t("Wähle eine Episode oder aktiviere die Zufallswiedergabe.")}
                      </p>
                      <button
                        class="ghost small"
                        @click=${() => this.navigate("management")}
                      >
                        ${t("Episoden auswählen")}
                      </button>`
              }
            </div>
            <div class="progress">
              <input
                type="range"
                min="0"
                max=${s?.duration || e?.duration || 1}
                .value=${String(this.seekDraft ?? this.displayElapsed)}
                aria-label=${t("Wiedergabeposition")}
                aria-valuetext=${t("{elapsed} von {duration}", { elapsed: fmt(this.displayElapsed), duration: fmt(s?.duration || 0) })}
                ?disabled=${!e || this.busy || s?.phase === "announcement"}
                @input=${(ev: Event) => (this.seekDraft = Number((ev.target as HTMLInputElement).value))}
                @change=${(ev: Event) => {
                  const seconds = Number((ev.target as HTMLInputElement).value);
                  void this.perform(async () => {
                    try {
                      this.state = await this.api("seek", "POST", {
                        position_seconds: seconds,
                      });
                    } finally {
                      if (this.seekDraft === seconds) this.seekDraft = null;
                    }
                  }, true);
                }}
              />
              <div class="time">
                <span>${fmt(this.seekDraft ?? this.displayElapsed)}</span
                ><span>${fmt(s?.duration || e?.duration || 0)}</span>
              </div>
            </div>
            <div class="controls">
              ${this.button("undo", t("Letztes Überspringen rückgängig"), "back", undefined, !s?.undo_available)}<button
                class="skip"
                data-action="rewind"
                aria-label=${t("30 Sekunden zurück")}
                ?disabled=${!e || this.busy || s?.phase === "announcement"}
              >
                ${icon("back")}<span>30</span></button
              ><button
                class="primary play"
                data-action="toggle"
                aria-label=${s?.state === "play" ? t("Pausieren") : t("Abspielen")}
                ?disabled=${this.busy || s?.state === "error" || !this.canPlay}
              >
                ${icon(s?.state === "play" ? "pause" : "play")}</button
              ><button
                class="skip"
                data-action="forward"
                aria-label=${t("30 Sekunden vor")}
                ?disabled=${!e || this.busy || s?.phase === "announcement"}
              >
                ${icon("forward")}<span>30</span></button
              >${this.button("next", this.nextLabel, "next", undefined, s?.state === "error" || !this.canNext)}
            </div>
          </div>
        </div>
        <div class="mode-row">
          <button
            class=${"ghost small " + (e?.bookmarked ? "on" : "")}
            data-action="bookmark"
            data-id=${e?.id || ""}
            aria-pressed=${!!e?.bookmarked}
            ?disabled=${!e || this.busy}
          >
            ${icon("bookmark")}${e?.bookmarked ? t("Für später gemerkt") : t("Für später merken")}</button
          ><button
            class=${"ghost small " + (s?.favorites_only ? "on" : "")}
            data-action="mode"
            aria-pressed=${!!s?.favorites_only}
          >
            ${icon("star")}${s?.favorites_only ? t("Nur Favoriten") : t("Alle Podcasts")}
          </button>
        </div>
        <div class="player-options">
          <div class="option">
            <label for="volume"
              >${this.target === "browser" ? t("Browser-Lautstärke") : t("MPD-Lautstärke")}</label
            >
            <div class="volume-line">
              <input
                id="volume"
                type="range"
                min="0"
                max="100"
                .value=${String(this.volumeDraft ?? Math.max(0, s?.volume || 0))}
                ?disabled=${!s || s.volume < 0 || this.busy}
                @input=${(ev: Event) => (this.volumeDraft = Number((ev.target as HTMLInputElement).value))}
                @change=${(ev: Event) => {
                  const value = Number((ev.target as HTMLInputElement).value);
                  void this.perform(async () => {
                    try {
                      this.state = await this.api("volume", "PUT", {
                        value,
                      });
                    } finally {
                      if (this.volumeDraft === value) this.volumeDraft = null;
                    }
                  }, true);
                }}
              /><output
                >${s && s.volume >= 0 ? (this.volumeDraft ?? s.volume) + " %" : "N/A"}</output
              >
            </div>
          </div>
          <div class="option timer-option">
            <div class="timer-settings">
              <div>
                <label for="timer">${t("Sleep-Timer")}</label
                ><select
                  id="timer"
                  ?disabled=${this.busy}
                  @change=${(ev: Event) => {
                    const minutes = Number(
                      (ev.target as HTMLSelectElement).value,
                    );
                    void this.perform(async () => {
                      this.state = await this.api("timer", "PUT", {
                        minutes,
                      });
                    }, true);
                  }}
                >
                  ${timerPresets.map((v) => html`<option value=${v} .selected=${live((s?.timer.minutes || 0) === v)}>${v ? v + t(" Minuten") : t("Aus")}</option>`)}
                </select>
              </div>
              <div class="random-option">
                <span class="option-label" id="random-label"
                  >${t("Zufallswiedergabe")}</span
                ><button
                  type="button"
                  class="target-switch random-switch"
                  role="switch"
                  aria-labelledby="random-label"
                  aria-checked=${!!s && s.when_queue_empty !== "stop"}
                  ?disabled=${!s || this.busy}
                  @click=${() =>
                    void this.perform(async () => {
                      this.state = await this.api("playback/random", "PUT", {
                        value: s?.when_queue_empty === "stop",
                      });
                    }, true)}
                >
                  <span class="switch-track" aria-hidden="true"
                    ><span></span></span
                  ><span
                    >${s && s.when_queue_empty !== "stop" ? t("An") : t("Aus")}</span
                  >
                </button>
              </div>
            </div>
            ${
              s?.state === "play" && s.timer.enabled
                ? html`<div class="timer-line">
                    <span class="timer-state"
                      >${fmt(this.displayRemaining) + (s.timer.suspended ? t(" · pausiert für Ansage") : s.phase === "announcement" && !s.timer.run_active ? t(" · ab Episode") : "")}</span
                    ><button
                      data-action="extend"
                      ?disabled=${!s?.timer.enabled || this.busy}
                    >
                      ${t("+5 Min.")}
                    </button>
                  </div>`
                : nothing
            }
            <details class="help-details">
              <summary>${t("Timer-Hinweise")}</summary>
              <p class="muted small">
                ${t("Pause und „Nächste“ behalten die verbleibende Timer-Zeit bei. Zufallswiedergabe greift, wenn die Warteschlange leer ist.")}
              </p>
            </details>
          </div>
        </div>
      </article>
      <div class="player-side">
        <article
          class="panel sleep-panel ${s?.sleep_mode ? "active" : "is-idle"}"
          aria-label=${t("Einschlafmodus")}
        >
          <div class="row spread">
            <h2>${icon("moon")} ${t("Einschlafen")}</h2>
          </div>
          <p class="muted small sleep-policy">
            ${t("Queue zuerst, danach")}
            ${(s?.sleep_mode ? s.when_queue_empty : this.config?.sleep_defaults.when_queue_empty) === "random" ? t("zufällig aus allen Episoden") : t("zufällig aus nicht gehörten Episoden")}.
          </p>
          <p class="sleep-time">
            ${s?.sleep_mode ? fmt(this.displayRemaining) : (this.config?.sleep_defaults.minutes || 15) + t(" Minuten")}${s?.sleep_mode && s.state !== "play" ? html`<span class="muted small"> ${t("· pausiert")}</span>` : nothing}
          </p>
          <div class="sleep-actions">
            <button
              class="primary sleep-start"
              data-action="sleep"
              ?disabled=${this.busy || s?.state === "error"}
            >
              ${icon(s?.sleep_mode && s.state === "play" ? "pause" : "play")}${!s?.sleep_mode ? t("Einschlafen starten") : s.state === "play" ? t("Pause") : t("Fortsetzen")}
            </button>
            <button
              class="sleep-extend"
              data-action="extend"
              ?disabled=${!s?.sleep_mode || this.busy}
            >
              ${t("+5 Min.")}
            </button>
            ${this.button("next", this.nextLabel, "next", undefined, !s?.sleep_mode || !this.canNext || s?.state === "error")}
          </div>
          ${s?.sleep_mode ? html`<button class="ghost small" data-action="normal">${t("Einschlafmodus beenden")}</button>` : html`<button class="ghost small" @click=${() => this.navigate("config/sleep")}>${t("Vorgaben ändern")}</button>`}
        </article>
        <aside class="panel">
          <div class="panel-head">
            <div>
              <h2>${t("Als Nächstes")}</h2>
              <p class="muted small">
                ${countText(s?.queue.length || 0, "{count} Episode", "{count} Episoden")}
                ·
                ${Math.round((s?.queue || []).reduce((sum, e) => sum + e.duration, 0) / 60)}
                ${t("Min.")}${s?.queue.some((e) => !e.duration) ? " + unbekannte Dauer" : ""}
              </p>
            </div>
            <button
              class="ghost small"
              data-action="clear"
              ?disabled=${!s?.queue.length || this.busy}
            >
              ${t("Leeren")}
            </button>
          </div>
          <div class="list">
            ${s?.queue.length ? s.queue.map((ep, i) => this.queueItem(ep, i)) : html`<div class="empty">${t("Warteschlange leer.")}</div>`}
          </div>
          <details class="help-details">
            <summary>${t("Wiedergaberegeln")}</summary>
            <p class="queue-foot">
              ${s?.when_queue_empty === "stop" ? t("Nach der Warteschlange stoppt die Wiedergabe.") : s?.when_queue_empty === "random_unheard" ? t("Danach zufällig aus nicht gehörten Episoden wählen und von vorne starten.") : t("Danach zufällig aus allen Episoden wählen und von vorne starten.")}
              ${s?.timer.enabled ? t(" Ein aktiver Timer läuft bei automatischen Folgenwechseln weiter.") : ""}
            </p>
          </details>
          <button
            class="ghost"
            style="width:100%;margin-top:16px"
            @click=${() => this.navigate("management")}
          >
            ${icon("plus")}${t("Episoden auswählen")}
          </button>
        </aside>
      </div>
    </div>
    <p class="bottom-note keyboard-help">
      ${t("Leertaste: Play/Pause · ← / →: 30 Sekunden · ↑ / ↓: Lautstärke ±5 % · N: Nächste · P: Player")}
    </p>
  </section>`;
}
export function queueItem(this: PlayPodApp, e: Episode, i: number) {
  return html`<article
    class="queue-item"
    draggable="true"
    @dragstart=${(ev: DragEvent) => {
      this.dragId = e.id;
      ev.dataTransfer?.setData("text/plain", String(e.id));
    }}
    @dragover=${(ev: DragEvent) => ev.preventDefault()}
    @drop=${(ev: DragEvent) => {
      ev.preventDefault();
      const id = this.dragId;
      this.dragId = null;
      if (!id || id === e.id || !this.state) return;
      const ids = this.state.queue.map((e) => e.id).filter((x) => x !== id);
      ids.splice(ids.indexOf(e.id), 0, id);
      void this.perform(() => this.order(ids));
    }}
  >
    <div class="item-top">
      <span class="queue-number">${i + 1}</span>${this.cover(e)}
      <div class="item-text">
        <p>
          ${e.podcast} · ${e.duration ? fmt(e.duration) : t("Dauer unbekannt")}
        </p>
        <h3>${e.title}</h3>
        ${e.source_type === "web" ? downloadInfo.call(this, e) : nothing}
        ${e.queue_error ? html`<span class="tag error-tag">${localizeMessage(e.queue_error)}</span>` : nothing}
      </div>
    </div>
    <div class="item-actions">
      ${this.button("up", e.title + t(" nach oben"), "up", e.id, i === 0)}${this.button("down", e.title + t(" nach unten"), "down", e.id, i === (this.state?.queue.length || 0) - 1)}<button
        class="ghost"
        data-action="first"
        data-id=${e.id}
        ?disabled=${i === 0 || this.busy}
      >
        ${t("Als Nächstes")}</button
      >${this.button(e.queue_error ? "retry" : "play", e.queue_error ? t("Erneut freigeben") : t("Jetzt abspielen"), e.queue_error ? "back" : "play", e.id)}${this.button("queue-remove", t("Eintrag entfernen"), "close", e.id)}
    </div>
  </article>`;
}
export function mini(this: PlayPodApp) {
  const s = this.state!;
  const duration = s.duration || s.current?.duration || 0;
  const progress =
    duration > 0 ? Math.min(1, Math.max(0, this.displayElapsed / duration)) : 0;
  return html`<div class="mini-player">
    ${this.cover(s.current)}<button
      class="mini-name"
      title=${s.current?.title || t("Player öffnen")}
      @click=${() => this.navigate("player")}
    >
      <strong>${s.current?.title || t("Player öffnen")}</strong
      ><span
        >${s.phase === "announcement" ? this.announcementLabel + " · " + (s.announcement_kind === "mode" || s.announcement_kind === "custom" ? s.announcement_text : s.current?.podcast || "") : s.current?.podcast || t("Keine Episode ausgewählt")}</span
      ></button
    >${s.state === "play" && s.timer.enabled ? html`<span class="timer-state">${fmt(this.displayRemaining)}</span>` : nothing}
    <button
      class="icon primary"
      data-action="toggle"
      aria-label=${s.state === "play" ? t("Pausieren") : t("Abspielen")}
      ?disabled=${this.busy || s.state === "error" || !this.canPlay}
    >
      ${icon(s.state === "play" ? "pause" : "play")}</button
    >${this.button("next", this.nextLabel, "next", undefined, s.state === "error" || !this.canNext)}
    ${duration > 0 ? html`<div class="mini-progress" aria-hidden="true"><span style=${`transform: scaleX(${progress})`}></span></div>` : nothing}
  </div>`;
}

function playbackTarget(this: PlayPodApp) {
  const state = this.state;
  return html`<div class="playback-target">
    <span class="badge playback-status"
      >${state?.waiting_download ? t("Wartet auf Download") : state?.phase === "announcement" ? (state.state === "pause" ? this.announcementLabel + t(" pausiert") : this.announcementLabel + t(" läuft")) : state?.state === "play" ? t("Wiedergabe läuft") : state?.state === "pause" ? t("Pausiert") : t("Gestoppt")}</span
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
              <span class="switch-track" aria-hidden="true"><span></span></span>
              <span id="target-label">${t("In diesem Browser abspielen")}</span>
            </button>
          </div>`
        : html`<span class="badge">${t("Dieser Browser")}</span>`
    }
    ${this.config?.mpd_configured ? html`<span class="target-hint">${this.target === "browser" ? t("Eigene Queue · MPD läuft unabhängig") : "MPD"}</span>` : nothing}
  </div>`;
}
