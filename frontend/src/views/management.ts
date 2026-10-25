import { t, localeTag, localizeMessage, countText } from "../i18n";
import { html, nothing } from "lit";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import type { PlayPodApp } from "../main";
import type { Episode, Feed, Job } from "../types";
import { fmt, date, icon } from "../ui";
export function renderManagement(this: PlayPodApp) {
  return html`<section aria-label=${t("Management")}>
    ${!this.managementLoaded ? html`<p class="notice" role="status">${t("Katalog wird geladen …")}</p>` : nothing}
    <div class="tools">
      <div class="search">
        <input
          type="search"
          placeholder=${t("Podcast oder Episode suchen …")}
          aria-label=${t("Podcast oder Episode suchen")}
          .value=${this.query}
          @input=${(ev: Event) => {
            this.query = (ev.target as HTMLInputElement).value;
            this.feedFilter = null;
            this.offset = 0;
            clearTimeout(this.searchTimer);
            this.searchTimer = window.setTimeout(
              () => void this.loadManagement(),
              200,
            );
          }}
        />
      </div>
      <div class="row">
        <button class="ghost" data-action="downloads">
          ${t("Downloads verwalten")}
        </button>
        <button
          class="ghost"
          data-action="link-add"
          ?disabled=${!this.downloads.enabled || !this.downloads.ytdlp_enabled}
        >
          ${t("Video-/Audiolink hinzufügen")}
        </button>
        <button
          class="ghost"
          data-action="scan-media"
          ?disabled=${this.busy || !this.config?.media_roots.some((r) => r.enabled)}
        >
          ${t("Lokale Medien einlesen")}
        </button>
        <button class="ghost" data-action="cleanup">${t("Aufräumen")}</button
        ><button class="primary" data-action="feed-add">
          ${icon("plus")}${t("Podcast hinzufügen")}
        </button>
      </div>
    </div>
    ${this.downloads.enabled && this.downloads.error ? html`<p class="notice" role="status">${localizeMessage(this.downloads.error)}</p>` : nothing}
    <div class="tabs">
      ${[
        ["all", t("Alle")],
        ["marked", t("Für später")],
        ["new", t("Ungehört")],
        ["started", t("Angespielt")],
        ["completed", t("Gehört")],
        ["local", t("Lokale Medien")],
        ["downloaded", t("Heruntergeladen")],
      ].map(
        ([v, t]) =>
          html`<button
            class=${this.filter === v ? "active" : ""}
            @click=${() => {
              this.filter = v;
              this.offset = 0;
              void this.loadManagement();
            }}
          >
            ${t}
          </button>`,
      )}${
        this.feedFilter
          ? html`<button
              class="active"
              @click=${() => {
                this.feedFilter = null;
                this.offset = 0;
                void this.loadManagement();
              }}
            >
              ${this.feeds.find((f) => f.id === this.feedFilter)?.title} ×
            </button>`
          : nothing
      }
    </div>
    <div class="panel-head">
      <h2>${t("Podcasts und Importe")}</h2>
      <button class="ghost small" data-action="refresh" ?disabled=${this.busy}>
        ${t("Alle aktualisieren")}
      </button>
    </div>
    ${this.jobs.filter((j) => j.state === "running").map((j) => html`<div class="notice" role="status">${j.kind === "refresh" ? t("Feedaktualisierung") : j.kind === "media" ? t("Lokale Verzeichnisse") : t("URL-Prüfung")} · ${j.progress}/${j.total}</div>`)}
    <div class="feed-grid">
      ${this.feeds
        .filter((f) => !this.feedFilter || f.id === this.feedFilter)
        .map(
          (f) =>
            html`<article class="feed-card">
              <div class="row spread">
                ${this.cover(f)}<button
                  class=${"icon ghost " + (f.favorite ? "on" : "")}
                  data-action="favorite"
                  data-id=${f.id}
                  aria-label=${f.favorite ? t("Favorit entfernen") : t("Favorisieren")}
                  aria-pressed=${!!f.favorite}
                >
                  ${icon("star")}
                </button>
              </div>
              <h3>${f.title}</h3>
              ${f.kind === "local" ? html`<span class="tag">${t("Lokales Verzeichnis")}</span>` : f.kind === "links" ? html`<span class="tag">${t("YT-Importe · Audio")}</span>` : nothing}
              <p>
                ${countText(f.episode_count, "{count} Episode", "{count} Episoden")}
                ·
                ${f.kind === "links" ? t("Manuell importiert") : f.last_success ? t("Aktualisiert ") + date(f.last_success) : t("Noch nicht aktualisiert")}
              </p>
              ${f.error ? html`<p class="error-tag">${localizeMessage(f.error)}</p>` : nothing}
              <div class="row">
                <button
                  class="ghost"
                  @click=${() => {
                    void this.selectFeed(f.id);
                  }}
                >
                  ${t("Episoden")}</button
                >${f.kind !== "links" ? this.button("refresh", f.kind === "local" ? t("Verzeichnisse einlesen") : t("Diesen Feed aktualisieren"), "back", f.id) : nothing}${f.kind === "rss" && this.downloads.enabled ? html`<button class="ghost small" data-action="feed-download" data-id=${f.id} ?disabled=${this.busy}>${t("Ungehörte herunterladen")}</button>` : nothing}${f.kind === "rss" ? html`${this.button("feed-edit", t("Feed bearbeiten"), "config", f.id)}` : nothing}${f.kind === "links" ? this.button("link-clear", t("Importliste leeren"), "close", f.id, !f.episode_count) : f.kind !== "local" ? this.button("feed-delete", t("Podcast löschen"), "close", f.id) : nothing}
              </div>
            </article>`,
        )}
    </div>
    ${this.managementLoaded && !this.feeds.length ? html`<div class="empty">${this.query ? t("Keine Podcasts oder Episoden zur Suche gefunden.") : t("Noch keine Podcasts oder Importe vorhanden. Podcast per RSS-URL oder Video-/Audiolink hinzufügen.")}</div>` : nothing}
    <article class="panel anchored-section" id="episode-list" tabindex="-1">
      <div class="panel-head">
        <h2>${t("Episoden")}</h2>
        <span class="muted small">${this.total} ${t("Einträge")}</span>
      </div>
      ${this.episodes.map(
        (e) =>
          html`<article
            class="episode-row anchored-section ${this.highlightedEpisode === e.id ? "episode-highlight" : ""}"
            id=${`episode-${e.id}`}
            tabindex="-1"
          >
            ${this.cover(e)}
            <div class="item-text">
              <p>
                ${e.podcast} · ${date(e.published)} ·
                ${e.duration ? fmt(e.duration) : t("Dauer unbekannt")}
              </p>
              <h3>
                <button
                  class="ghost"
                  style="padding:0;border:0;min-height:30px;text-align:left;justify-content:flex-start"
                  data-action="details"
                  data-id=${e.id}
                >
                  ${e.title}
                </button>
              </h3>
              ${downloadInfo.call(this, e)}
              <span class="tag"
                >${e.completed ? t("Gehört") : e.last_started ? t("Angespielt · ") + fmt(e.position) : t("Ungehört")}</span
              >${e.local_source ? html` <span class="tag ${e.source_present ? "" : "error-tag"}">${e.source_present ? t("Lokale Datei") : e.availability === "local_pending" ? t("Datei noch nicht bereit") : e.availability === "local_unconfigured" ? t("Verzeichnis deaktiviert") : t("Datei fehlt")}</span>` : nothing}${this.state?.queue.some((q) => q.id === e.id) ? html` <span class="tag">${t("In Warteschlange")}</span>` : nothing}${e.availability === "unreachable" ? html` <span class="tag error-tag">${t("Quelle nicht erreichbar")}</span>` : nothing}
            </div>
            <div class="episode-actions">
              ${downloadButton.call(this, e)}
              <button
                class=${"icon ghost " + (e.bookmarked ? "on" : "")}
                data-action="bookmark"
                data-id=${e.id}
                aria-label=${e.bookmarked ? t("Merker entfernen") : t("Für später merken")}
                aria-pressed=${!!e.bookmarked}
              >
                ${icon("bookmark")}</button
              ><button
                class="ghost"
                data-action="enqueue"
                data-id=${e.id}
                ?disabled=${this.busy}
              >
                ${icon("plus")}${t("Anhängen")}</button
              ><button
                class="primary"
                data-action="play"
                data-id=${e.id}
                ?disabled=${this.busy || (e.source_type === "web" && !this.downloads.items.some((d) => d.episode_id === e.id && d.state === "ready"))}
              >
                ${icon("play")}${t("Abspielen")}
              </button>
            </div>
          </article>`,
      )}${this.managementLoaded && !this.episodes.length ? html`<div class="empty">${t("Keine Episoden für diesen Filter.")}</div>` : nothing}
      <div class="row spread pagination">
        <button
          class="ghost"
          ?disabled=${this.offset === 0}
          @click=${() => {
            this.offset = Math.max(0, this.offset - 50);
            void this.loadManagement();
          }}
        >
          ${t("Zurück")}</button
        ><span class="muted small"
          >${this.total ? this.offset + 1 : 0}–${Math.min(this.offset + 50, this.total)}
          ${t("von")} ${this.total}</span
        ><button
          class="ghost"
          ?disabled=${this.offset + 50 >= this.total}
          @click=${() => {
            this.offset += 50;
            void this.loadManagement();
          }}
        >
          ${t("Weitere")}
        </button>
      </div>
    </article>
  </section>`;
}

function downloadInfo(this: PlayPodApp, e: Episode) {
  const d = this.downloads.items.find((d) => d.episode_id === e.id);
  if (!d) return nothing;
  const amount = `${(d.received / 1048576).toLocaleString(localeTag(), { maximumFractionDigits: 1 })} MB`;
  const text =
    d.state === "ready"
      ? this.downloads.online
        ? t("Heruntergeladen · ") + amount
        : t("Heruntergeladen")
      : d.state === "running"
        ? (d.phase === "processing"
            ? t("Audio wird vorbereitet · ")
            : t("Download · ")) +
          (d.total
            ? `${Math.min(100, Math.floor((d.received / d.total) * 100))} % · `
            : "") +
          amount
        : d.state === "queued"
          ? t("Download wartet")
          : d.state === "cancel_requested"
            ? t("Download wird abgebrochen …")
            : d.state === "deleted"
              ? t("Lokale Kopie gelöscht")
              : d.state === "cancelled"
                ? t("Download abgebrochen")
                : localizeMessage(d.error) || t("Download fehlgeschlagen");
  return html`<p
    class=${d.state === "error" || d.state === "missing" ? "error-tag small" : "muted small"}
  >
    ${text}
  </p>`;
}

function downloadButton(this: PlayPodApp, e: Episode) {
  if (!this.downloads.enabled || !e.url || e.local_source) return nothing;
  const d = this.downloads.items.find((d) => d.episode_id === e.id);
  if (d?.state === "ready") return nothing;
  const pending =
    d && ["queued", "running", "cancel_requested"].includes(d.state);
  return html`<button
    class="ghost"
    data-action=${pending ? "download-cancel" : "download"}
    data-id=${e.id}
    ?disabled=${this.busy || d?.state === "cancel_requested"}
    aria-label=${(pending ? t("Download abbrechen: ") : t("Episode herunterladen: ")) + e.title}
  >
    ${pending ? t("Abbrechen") : d ? t("Erneut laden") : t("Herunterladen")}
  </button>`;
}
