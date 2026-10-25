import { html, nothing } from "lit";
import { t, localeTag, localizeMessage, countText } from "../i18n";
import { groupActivity, managementLink } from "../activity";
import type { PlayPodApp } from "../main";

export function renderActivity(this: PlayPodApp) {
  return html`<section aria-label=${t("Aktivität")}>
    <div class="tabs" aria-label=${t("Aktivität filtern")}>
      ${[
        ["all", t("Alle")],
        ["new", t("Neue Episoden")],
        ["completed", t("Gehört")],
      ].map(
        ([value, label]) =>
          html` <button
            class=${this.activityFilter === value ? "active" : ""}
            aria-pressed=${this.activityFilter === value}
            @click=${() => this.setActivityFilter(value)}
          >
            ${label}
          </button>`,
      )}
    </div>
    <p class="muted small">
      ${t("Ereignisse der letzten 90 Tage. Zeitpunkte entsprechen deiner lokalen Zeitzone.")}
    </p>
    ${this.activityError ? html`<p class="notice" role="alert">${localizeMessage(this.activityError)}</p>` : nothing}
    ${!this.activityLoaded ? html`<p role="status">${t("Aktivität wird geladen …")}</p>` : nothing}
    ${groupActivity(this.activityItems).map(
      (group) =>
        html`<section class="activity-day">
          <h2>
            ${group.day.toLocaleDateString(localeTag(), { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </h2>
          <div class="panel activity-list">
            ${group.items.map((event) => {
              const link = managementLink(event);
              const label =
                event.kind === "completed"
                  ? t("Zu Ende gehört")
                  : event.kind === "feed_added"
                    ? t("Podcast hinzugefügt")
                    : t("Neue Episode");
              return html`<article class="activity-row">
                <time datetime=${new Date(event.created * 1000).toISOString()}
                  >${new Date(event.created * 1000).toLocaleTimeString(localeTag(), { hour: "2-digit", minute: "2-digit" })}</time
                >
                <div class="item-text">
                  <p class="activity-label">
                    ${label}${event.kind === "completed" ? html` · ${event.target === "browser" ? t("Browser") : "MPD"}` : nothing}
                  </p>
                  <h3>
                    ${link ? html`<a href=${link}>${event.kind === "feed_added" ? event.podcast : event.title}</a>` : event.kind === "feed_added" ? event.podcast : event.title}
                  </h3>
                  <p class="muted small">
                    ${event.kind === "feed_added" ? countText(event.count, "{count} Episode", "{count} Episoden") : event.podcast}${!link ? html` · ${t("Inzwischen gelöscht")}` : nothing}
                  </p>
                </div>
              </article>`;
            })}
          </div>
        </section>`,
    )}
    ${this.activityLoaded && !this.activityItems.length && !this.activityError ? html`<div class="empty">${t("Noch keine Ereignisse für diesen Filter.")}</div>` : nothing}
    ${this.activityCursor ? html`<button class="ghost" ?disabled=${this.activityLoading} @click=${() => void this.loadActivity(true)}>${t("Weitere")}</button>` : nothing}
  </section>`;
}
