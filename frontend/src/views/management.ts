import { t, localeTag, localizeMessage, countText } from "../i18n";
import { html, nothing } from "lit";
import { repeat } from "lit/directives/repeat.js";
import type { PlayPodApp } from "../main";
import type { Episode, Feed } from "../types";
import { fmt, date, icon } from "../ui";
export function renderManagement(this: PlayPodApp) {
  const selected = this.feeds.find((f) => f.id === this.feedFilter);
  const choose = async (id: number | null) => {
    const picker =
      this.renderRoot.querySelector<HTMLDetailsElement>(".podcast-picker");
    if (picker?.open) {
      picker.open = false;
      picker.querySelector("summary")?.focus();
    }
    this.feedFilter = id;
    this.offset = 0;
    this.highlightedEpisode = null;
    await this.loadManagement();
  };
  const podcasts = () =>
    html`<nav class="podcast-list" aria-label=${t("Podcasts")}>
      <button
        class=${this.feedFilter === null ? "selected" : ""}
        aria-pressed=${this.feedFilter === null}
        @click=${() => void choose(null)}
      >
        ${t("Alle Podcasts")}
      </button>
      ${this.feeds.map(
        (f) =>
          html`<button
            class=${this.feedFilter === f.id ? "selected" : ""}
            aria-pressed=${this.feedFilter === f.id}
            @click=${() => void choose(f.id)}
          >
            ${this.cover(f)}<span class="podcast-name"
              ><strong>${f.title}</strong
              ><small
                >${countText(f.episode_count, "{count} Episode", "{count} Episoden")}${f.error ? html` · <span class="error-tag">${t("Fehler")}</span>` : nothing}</small
              ></span
            >${f.favorite ? icon("star") : nothing}
          </button>`,
      )}
    </nav>`;
  return html`<section aria-label=${t("Bibliothek")}>
    <div class="library-tools">
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
      <button
        class="ghost"
        data-action="link-add"
        ?disabled=${!this.downloads.enabled || !this.downloads.ytdlp_enabled}
      >
        <span class="desktop-label">${t("Link importieren")}</span
        ><span class="mobile-label">${t("Import")}</span>
      </button>
      <button class="primary" data-action="feed-add">
        ${icon("plus")}<span class="desktop-label"
          >${t("Podcast hinzufügen")}</span
        ><span class="mobile-label">${t("Podcast")}</span>
      </button>
    </div>
    ${this.downloads.error ? html`<p class="notice error-tag" role="alert">${localizeMessage(this.downloads.error)}</p>` : nothing}
    ${this.jobs.filter((j) => j.state === "running").map((j) => html`<p class="notice" role="status">${j.kind === "refresh" ? t("Feedaktualisierung") : j.kind === "media" ? t("Lokale Verzeichnisse") : t("URL-Prüfung")} · ${j.progress}/${j.total}</p>`)}
    <div class="library-layout">
      <aside class="podcast-sidebar">
        <div class="panel-head">
          <h2>${t("Podcasts")}</h2>
          ${this.button("refresh", t("Alle aktualisieren"), "refresh")}
        </div>
        ${podcasts()}
        <details class="podcast-picker">
          <summary>
            ${selected ? this.cover(selected) : icon("library")}
            <span class="podcast-name"
              ><small>${t("Podcast auswählen")}</small
              ><strong>${selected?.title || t("Alle Podcasts")}</strong></span
            >
            <span class="picker-chevron" aria-hidden="true">⌄</span>
          </summary>
          ${podcasts()}
        </details>
      </aside>
      <article
        class="library-episodes anchored-section"
        id="episode-list"
        tabindex="-1"
      >
        <div class="library-heading">
          <div>
            <h2>${selected?.title || t("Episoden")}</h2>
            <p class="muted small">
              ${countText(this.total, "{count} Episode", "{count} Episoden")}
            </p>
          </div>
          ${selected ? feedActions.call(this, selected) : html`<button class="ghost small" data-action="cleanup">${t("Quellen prüfen")}</button>`}
        </div>
        ${selected?.error ? html`<p class="notice error-tag">${localizeMessage(selected.error)}</p>` : nothing}
        <div class="tabs" aria-label=${t("Episoden filtern")}>
          ${[
            ["all", t("Alle")],
            ["marked", t("Für später")],
            ["new", t("Ungehört")],
            ["started", t("Angespielt")],
            ["completed", t("Gehört")],
            ["local", t("Lokale Medien")],
            ["downloaded", t("Heruntergeladen")],
          ].map(
            ([value, label]) =>
              html`<button
                class=${this.filter === value ? "active" : ""}
                aria-pressed=${this.filter === value}
                @click=${() => {
                  this.filter = value;
                  this.offset = 0;
                  void this.loadManagement();
                }}
              >
                ${label}
              </button>`,
          )}
        </div>
        <label class="mobile-filter"
          >${t("Filter")}<select
            .value=${this.filter}
            @change=${(ev: Event) => {
              this.filter = (ev.target as HTMLSelectElement).value;
              this.offset = 0;
              void this.loadManagement();
            }}
          >
            ${[
              ["all", t("Alle")],
              ["marked", t("Für später")],
              ["new", t("Ungehört")],
              ["started", t("Angespielt")],
              ["completed", t("Gehört")],
              ["local", t("Lokale Medien")],
              ["downloaded", t("Heruntergeladen")],
            ].map(
              ([value, label]) =>
                html`<option value=${value}>${label}</option>`,
            )}
          </select></label
        >
        ${!this.managementLoaded ? html`<p class="notice" role="status">${t("Katalog wird geladen …")}</p>` : nothing}
        ${repeat(
          this.episodes,
          (e) => e.id,
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
                    class="episode-title"
                    data-action="details"
                    data-id=${e.id}
                  >
                    ${e.title}
                  </button>
                </h3>
                ${downloadInfo.call(this, e)}
                <span class="episode-status"
                  >${e.completed ? t("Gehört") : e.last_started ? t("Angespielt · ") + fmt(e.position) : t("Ungehört")}${this.state?.queue.some((q) => q.id === e.id) ? html` · ${t("In Warteschlange")}` : nothing}${e.availability === "unreachable" ? html` · <span class="error-tag">${t("Quelle nicht erreichbar")}</span>` : nothing}${e.local_source && !e.source_present ? html` · <span class="error-tag">${t("Datei fehlt")}</span>` : nothing}</span
                >
              </div>
              <div class="episode-actions">
                <button
                  class=${"icon ghost " + (e.bookmarked ? "on" : "")}
                  data-action="bookmark"
                  data-id=${e.id}
                  aria-label=${e.bookmarked ? t("Merker entfernen") : t("Für später merken")}
                  aria-pressed=${!!e.bookmarked}
                >
                  ${icon("bookmark")}
                </button>
                <button
                  class="ghost"
                  data-action="enqueue"
                  data-id=${e.id}
                  ?disabled=${this.busy}
                >
                  ${icon("plus")}<span>${t("Anhängen")}</span>
                </button>
                <button
                  class="primary"
                  data-action="play"
                  data-id=${e.id}
                  ?disabled=${this.busy || (e.source_type === "web" && !this.downloads.items.some((d) => d.episode_id === e.id && d.state === "ready"))}
                >
                  ${icon("play")}<span>${t("Abspielen")}</span>
                </button>
                <details class="action-menu">
                  <summary aria-label=${t("Weitere Aktionen")}>
                    ${icon("more")}
                  </summary>
                  <div class="menu-items">
                    <button class="ghost" data-action="details" data-id=${e.id}>
                      ${t("Beschreibung ansehen")}
                    </button>
                    ${downloadButton.call(this, e)}
                    ${e.local_source && !e.url ? html`<button class="ghost danger" data-action="remove-local" data-id=${e.id}>${t("Aus Katalog entfernen")}</button>` : nothing}
                  </div>
                </details>
              </div>
            </article>`,
        )}
        ${this.managementLoaded && !this.episodes.length ? html`<div class="empty">${this.query ? t("Keine Podcasts oder Episoden zur Suche gefunden.") : t("Keine Episoden für diesen Filter.")}</div>` : nothing}
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
    </div>
  </section>`;
}
function feedActions(this: PlayPodApp, f: Feed) {
  return html`<div class="feed-actions">
    ${f.kind === "rss" && this.downloads.enabled ? html`<button class="ghost small" data-action="feed-download" data-id=${f.id} ?disabled=${this.busy}>${t("Ungehörte herunterladen")}</button>` : nothing}${f.kind !== "local" ? html`<button class="ghost small" data-action="feed-delete-heard" data-id=${f.id} ?disabled=${this.busy}>${t("Gehörte Downloads löschen")}</button>` : nothing}
    <details class="action-menu">
      <summary aria-label=${t("Podcast-Aktionen")}>${icon("more")}</summary>
      <div class="menu-items">
        <button class="ghost" data-action="favorite" data-id=${f.id}>
          ${f.favorite ? t("Favorit entfernen") : t("Favorisieren")}
        </button>
        ${f.kind !== "links" ? html`<button class="ghost" data-action="refresh" data-id=${f.id}>${t("Aktualisieren")}</button>` : nothing}
        ${f.kind === "rss" ? html`<button class="ghost" data-action="feed-edit" data-id=${f.id}>${t("Podcast bearbeiten")}</button>` : nothing}
        <button class="ghost" data-action="cleanup">
          ${t("Quellen prüfen")}
        </button>
        ${f.kind === "links" ? html`<button class="ghost danger" data-action="link-clear" data-id=${f.id}>${t("Importliste leeren")}</button>` : f.kind === "rss" ? html`<button class="ghost danger" data-action="feed-delete" data-id=${f.id}>${t("Podcast löschen")}</button>` : nothing}
      </div>
    </details>
  </div>`;
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
  if (d?.state === "ready" || d?.state === "missing")
    return html`<button
        class="ghost danger"
        data-action="download-delete"
        data-id=${e.id}
        ?disabled=${this.busy || d.in_use}
      >
        ${t("Lokale Kopie löschen")}</button
      >${d.in_use ? html`<span class="small muted">${t("Wird gerade verwendet")}</span>` : nothing}`;
  const pending =
    d && ["queued", "running", "cancel_requested"].includes(d.state);
  return html`<button
    class="ghost"
    data-action=${pending ? "download-cancel" : "download"}
    data-id=${e.id}
    ?disabled=${this.busy || d?.state === "cancel_requested"}
  >
    ${pending ? t("Download abbrechen") : t("Herunterladen")}
  </button>`;
}
