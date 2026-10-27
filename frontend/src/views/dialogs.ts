import { t, localeTag, localizeMessage } from "../i18n";
import { html, nothing } from "lit";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import type { PlayPodApp } from "../main";
import type { Episode, Feed, Job } from "../types";
import { fmt, date, icon } from "../ui";
export function renderDialog(this: PlayPodApp) {
  const d = this.dialog,
    e = d?.episode;
  return html`<dialog
    @close=${() => {
      this.dialog = null;
      this.job = null;
    }}
    aria-labelledby="dialog-title"
  >
    <div class="row spread" style="margin:0 0 15px">
      <h2 id="dialog-title" style="margin:0">
        ${d?.kind === "link" ? t("YouTube importieren") : d?.kind === "details" ? e?.title : d?.kind === "feed" ? (d.feed ? t("Podcast bearbeiten") : t("Podcast hinzufügen")) : d?.kind === "cleanup" ? t("Nicht erreichbare Episoden") : d?.title}
      </h2>
      <button
        class="icon ghost"
        data-action="close"
        aria-label=${t("Dialog schließen")}
      >
        ${icon("close")}
      </button>
    </div>
    ${
      d?.kind === "link"
        ? linkForm.call(this)
        : d?.kind === "details" && e
          ? html`<p class="eyebrow">${e.podcast} · ${fmt(e.duration)}</p>
              <div class="shownotes">
                ${e.description ? unsafeHTML(e.description) : html`<p>${t("Keine Beschreibung vorhanden.")}</p>`}
              </div>
              ${
                e.source_type === "web"
                  ? html`<p class="notice">
                        ${t("Importierte Audiospur: Zum Abspielen wird eine heruntergeladene Kopie benötigt.")}
                      </p>
                      <a href=${e.url} target="_blank" rel="noopener noreferrer"
                        >${t("Originalseite öffnen ↗")}</a
                      >`
                  : nothing
              }
              ${e.local_source ? html`<p class="small muted">${t("Lokale Datei:")} ${e.local_source}</p>` : nothing}
              <div class="row">
                ${e.local_source && !e.url ? html`<button class="ghost danger" data-action="remove-local" data-id=${e.id}>${t("Aus Katalog entfernen")}</button>` : nothing}
                <button
                  class="ghost"
                  ?disabled=${this.busy}
                  @click=${() =>
                    void this.perform(async () => {
                      await this.api(`episodes/${e.id}/completed`, "PUT", {
                        value: !e.completed,
                      });
                      this.close();
                    })}
                >
                  ${e.completed ? t("Als ungehört markieren") : t("Als gehört markieren")}</button
                ><button
                  class="ghost"
                  ?disabled=${this.busy}
                  @click=${() =>
                    void this.perform(async () => {
                      this.state = await this.api("episodes/play", "POST", {
                        episode_id: e.id,
                        from_start: true,
                      });
                      this.close();
                    })}
                >
                  ${t("Von vorne")}</button
                ><button
                  class="primary"
                  ?disabled=${this.busy}
                  @click=${() =>
                    void this.perform(async () => {
                      await this.action("play", e.id);
                      this.close();
                    })}
                >
                  ${e.last_started && !e.completed ? t("Fortsetzen") : t("Abspielen")}
                </button>
              </div>`
          : d?.kind === "feed"
            ? this.feedForm(d.feed)
            : d?.kind === "confirm"
              ? html`<p>${d.body}</p>
                  <div class="row">
                    <button class="ghost" data-action="close">
                      ${t("Abbrechen")}</button
                    ><button
                      class="danger"
                      ?disabled=${this.busy}
                      @click=${() => void this.perform(d.confirm!)}
                    >
                      ${t("Bestätigen")}
                    </button>
                  </div>`
              : d?.kind === "cleanup"
                ? this.cleanupDialog()
                : nothing
    }
  </dialog>`;
}
export function feedForm(this: PlayPodApp, feed?: Feed) {
  return html`<form
    @submit=${(ev: SubmitEvent) => {
      ev.preventDefault();
      const form = ev.currentTarget as HTMLFormElement,
        data = new FormData(form);
      void this.perform(async () => {
        await this.api(
          feed ? "feeds/" + feed.id : "feeds",
          feed ? "PUT" : "POST",
          {
            url: String(data.get("url")),
            title: String(data.get("title")),
            favorite: data.get("favorite") === "on",
          },
        );
        this.close();
        this.notify(
          feed
            ? t("Podcast gespeichert.")
            : t("Podcast hinzugefügt. Feedabruf läuft."),
        );
      });
    }}
  >
    <label
      >${t("Anzeigename")}<input
        name="title"
        type="text"
        .value=${feed?.title || ""}
        placeholder=${t("Wird aus dem Feed übernommen")} /></label
    ><label
      >${t("RSS-Feed-URL")}<input
        name="url"
        type="url"
        required
        .value=${feed?.url || ""}
        placeholder="https://example.org/feed.xml" /></label
    ><label class="form-check"
      ><input
        name="favorite"
        type="checkbox"
        .checked=${!!feed?.favorite}
      />${t("Als Favorit markieren")}</label
    >
    <p class="small muted">
      ${t("Der Episodenkatalog wird beim Feedabruf aktualisiert. Der Anzeigename kann dabei durch den Feedtitel ersetzt werden.")}
    </p>
    <div class="row">
      <button type="button" class="ghost" data-action="close">
        ${t("Abbrechen")}</button
      ><button class="primary" ?disabled=${this.busy}>${t("Speichern")}</button>
    </div>
  </form>`;
}
export function cleanupDialog(this: PlayPodApp) {
  const j = this.job,
    failed =
      j?.results?.filter(
        (r) => r.status === "unreachable" || r.status === "temporary_error",
      ) || [];
  return html`<p>
      ${t("Originalquellen manuell prüfen. Es wird nichts automatisch gelöscht. Ein erreichbarer Server bestätigt noch nicht die vollständige Abspielbarkeit.")}
    </p>
    ${
      j
        ? html`<p class="small">
              ${j.progress}/${j.total} ${t("geprüft ·")}
              ${j.state === "running" ? t("Prüfung läuft") : j.state === "done" ? t("Abgeschlossen") : localizeMessage(j.error) || t("Unterbrochen")}
            </p>
            <form
              @submit=${(ev: SubmitEvent) => {
                ev.preventDefault();
                const data = new FormData(ev.currentTarget as HTMLFormElement),
                  ids = data.getAll("episode").map(Number);
                if (!ids.length) {
                  this.notify(t("Bitte Episoden auswählen."));
                  return;
                }
                const temporary = failed.some(
                  (r) => ids.includes(r.id) && r.status === "temporary_error",
                );
                this.confirm(
                  t("Episoden endgültig löschen?"),
                  t(
                    "{count} Episoden samt Merkern und Queue-Einträgen löschen? Eine zugehörige laufende Episode wird gestoppt.",
                    { count: ids.length },
                  ) +
                    (temporary
                      ? t(
                          " Achtung: Die Auswahl enthält temporäre Fehler. Diese Quellen könnten weiterhin verfügbar sein.",
                        )
                      : ""),
                  async () => {
                    await this.api("cleanup/delete", "POST", {
                      ids,
                      include_temporary: temporary,
                    });
                    this.close();
                  },
                );
              }}
            >
              ${failed.map(
                (r) =>
                  html`<label class="check"
                    ><input name="episode" type="checkbox" value=${r.id} /><span
                      >${this.episodes.find((e) => e.id === r.id)?.title || t("Episode #") + r.id}<br /><span
                        class="error-tag small"
                        >${localizeMessage(r.error)}${r.status === "temporary_error" ? t(" · möglicherweise nur vorübergehend") : ""}</span
                      ></span
                    ></label
                  >`,
              )}${j.state === "done" && !failed.length ? html`<p>${t("Keine definitiv fehlenden Quellen gefunden.")}</p>` : nothing}${j.results?.filter((r) => r.status === "temporary_error").map((r) => html`<p class="small muted">${t("Episode #")}${r.id}: ${localizeMessage(r.error)} ${t("– nicht automatisch zum Löschen angeboten.")}</p>`)}${failed.length && j.state === "done" ? html`<div class="row"><button class="danger">${t("Ausgewählte löschen")}</button></div>` : nothing}
            </form>`
        : nothing
    }
    <div class="row">
      <button class="ghost" data-action="close">${t("Schließen")}</button
      ><button
        class="primary"
        ?disabled=${this.busy || j?.state === "running"}
        @click=${() =>
          void this.perform(async () => {
            const r = await this.api<{ job_id: string }>(
              "cleanup/checks",
              "POST",
            );
            this.job = await this.api<Job>("jobs/" + r.job_id);
          })}
      >
        ${j ? t("Erneut prüfen") : t("Prüfung starten")}
      </button>
    </div>`;
}

function linkForm(this: PlayPodApp) {
  return html`<form
    class="link-form"
    @submit=${(event: SubmitEvent) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget as HTMLFormElement);
      void this.perform(async () => {
        if (this.linkKind === "single") {
          await this.api("links", "POST", { url: String(data.get("url")) });
          this.notify(t("Link hinzugefügt. Audiospur wird heruntergeladen."));
        } else {
          await this.api("youtube/collections", "POST", {
            url: String(data.get("url")),
            kind: this.linkKind,
            limit: this.linkAll ? null : Number(data.get("limit")),
          });
          this.notify(
            t(
              "Sammlung hinzugefügt. Einträge werden ohne Download eingelesen.",
            ),
          );
        }
        this.close();
      });
    }}
  >
    <p class="muted small">
      ${t("Einzelimporte werden direkt heruntergeladen. Playlists und Kanäle werden regelmäßig ohne Audiodownload eingelesen. Shorts sowie laufende oder geplante Livestreams werden ausgeschlossen. Aufzeichnungen sind erlaubt.")}
    </p>
    <label
      >${t("Importart")}<select
        .value=${this.linkKind}
        @change=${(ev: Event) => (this.linkKind = (ev.target as HTMLSelectElement).value)}
      >
        <option value="single">${t("Einzelnes Video")}</option>
        <option value="yt_playlist">${t("YouTube-Playlist")}</option>
        <option value="yt_channel">${t("YouTube-Kanal")}</option>
      </select></label
    >
    ${
      this.linkKind !== "single"
        ? html`
            <label class="check"
              ><input
                type="checkbox"
                .checked=${this.linkAll}
                @change=${(ev: Event) => (this.linkAll = (ev.target as HTMLInputElement).checked)}
              />${t("Alle vorhandenen Videos einlesen")}</label
            >
            <label
              >${t("Anzahl beim ersten Import")}<input
                name="limit"
                type="number"
                min="1"
                max="100000"
                value="50"
                ?required=${!this.linkAll}
                ?disabled=${this.linkAll}
            /></label>
            <p class="muted small">
              ${t("Beim Kanal werden die neuesten Videos gewählt, bei Playlists die ersten Einträge in Playlist-Reihenfolge. Spätere neue Videos werden ergänzt.")}
            </p>
          `
        : nothing
    }
    <label
      >${t("Video-/Audio-URL")}<input
        name="url"
        type="url"
        required
        maxlength="4000"
        placeholder=${this.linkKind === "yt_playlist" ? "https://www.youtube.com/playlist?list=…" : this.linkKind === "yt_channel" ? "https://www.youtube.com/@kanal" : "https://www.youtube.com/watch?v=…"}
    /></label>
    <button class="primary" type="submit" ?disabled=${this.busy}>
      ${this.linkKind === "single" ? t("Hinzufügen und herunterladen") : t("Sammlung hinzufügen")}
    </button>
  </form>`;
}
