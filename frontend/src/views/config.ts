import {
  t,
  countText,
  localeTag,
  getLanguagePreference,
  setLanguage,
  type LanguagePreference,
  localizeMessage,
} from "../i18n";
import { html, nothing } from "lit";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import type { PlayPodApp } from "../main";
import type { Episode, Feed, Job } from "../types";
import { fmt, date, icon } from "../ui";
export function renderConfig(this: PlayPodApp) {
  const c = this.config;
  const storage = this.downloads.storage;
  const mb = (value: number) =>
    (value / 1048576).toLocaleString(localeTag(), {
      maximumFractionDigits: 1,
    }) + " MB";
  return html`<section class="settings-view" aria-label=${t("Einstellungen")}>
    <article class="panel language-panel">
      <label for="language">${t("Sprache")}</label>
      <select
        id="language"
        .value=${getLanguagePreference()}
        @change=${(ev: Event) => setLanguage((ev.target as HTMLSelectElement).value as LanguagePreference)}
      >
        <option value="auto" .selected=${getLanguagePreference() === "auto"}>
          ${t("Automatisch")}
        </option>
        <option value="de" .selected=${getLanguagePreference() === "de"}>
          Deutsch
        </option>
        <option value="en" .selected=${getLanguagePreference() === "en"}>
          English
        </option>
      </select>
    </article>
    <article
      class="settings-section anchored-section"
      id="sleep-config"
      tabindex="-1"
    >
      <h2>${t("Einschlafmodus")}</h2>
      <form
        class="sleep-config"
        @submit=${(ev: SubmitEvent) => {
          ev.preventDefault();
          if (this.savingSleep) return;
          const data = new FormData(ev.currentTarget as HTMLFormElement);
          this.savingSleep = true;
          void this.perform(async () => {
            try {
              const defaults = await this.api<
                NonNullable<typeof c>["sleep_defaults"]
              >("config/sleep", "PUT", {
                minutes: Number(data.get("minutes")),
                when_queue_empty: String(data.get("when_queue_empty")),
              });
              if (this.config)
                this.config = { ...this.config, sleep_defaults: defaults };
              if (this.browser) this.browser.sleepDefaults = defaults;
              this.notify(t("Einschlaf-Vorgaben gespeichert."));
            } finally {
              this.savingSleep = false;
            }
          }, true);
        }}
      >
        <label
          >${t("Laufzeit in Minuten")}<input
            name="minutes"
            type="number"
            min="1"
            max="1440"
            required
            .value=${String(c?.sleep_defaults.minutes || 15)}
        /></label>
        <label
          >${t("Wenn die Warteschlange leer ist")}<select
            name="when_queue_empty"
          >
            <option
              value="random_unheard"
              .selected=${c?.sleep_defaults.when_queue_empty !== "random"}
            >
              ${t("Zufällig · nicht vollständig gehört")}
            </option>
            <option
              value="random"
              .selected=${c?.sleep_defaults.when_queue_empty === "random"}
            >
              ${t("Zufällig · alle Episoden")}
            </option>
          </select></label
        >
        <button
          class="primary"
          type="submit"
          ?disabled=${this.savingSleep}
          aria-busy=${this.savingSleep}
        >
          ${this.savingSleep ? t("Speichert …") : t("Speichern")}
        </button>
      </form>
      <details class="help-details">
        <summary>${t("Hinweise zum Einschlafmodus")}</summary>
        <p class="muted small">
          ${t("Zufällige Episoden starten von vorne. Angefangene Folgen zählen als nicht vollständig gehört. Ohne passende Folge stoppt die Wiedergabe. Änderungen gelten beim nächsten Aktivieren; laufende Wiedergabe bleibt unverändert.")}
        </p>
      </details>
    </article>
    <article class="settings-section">
      <h2>${t("Downloads und Speicher")}</h2>
      <p>
        ${countText(storage.count, "{count} lokale Kopie", "{count} lokale Kopien")}
        · ${mb(storage.bytes)} · ${mb(storage.free_bytes)} ${t("frei")}
      </p>
      ${this.downloads.error ? html`<p class="notice error-tag">${localizeMessage(this.downloads.error)}</p>` : nothing}
      ${
        storage.orphan_bytes
          ? html`<p>
                ${mb(storage.orphan_bytes)} ${t("ohne Episodenzuordnung")}
              </p>
              <button
                class="ghost danger"
                data-action="downloads-cleanup"
                ?disabled=${this.busy}
              >
                ${t("Verwaiste Dateien löschen")}
              </button>`
          : html`<p class="muted small">${t("Keine verwaisten Downloads.")}</p>`
      }
      <details class="help-details">
        <summary>${t("Was wird gelöscht?")}</summary>
        <p>
          ${t("Nur lokale Downloadkopien werden gelöscht. Episoden, Merker und Hörfortschritt bleiben erhalten. Externe Dateien werden nur gelesen.")}
        </p>
      </details>
    </article>
    <article class="settings-section">
      <div class="panel-head">
        <div>
          <h2>${t("Lokale Medien")}</h2>
          <p class="muted small">
            ${t("Externe Verzeichnisse werden nur gelesen.")}
          </p>
        </div>
        <button
          class="ghost"
          data-action="scan-media"
          ?disabled=${this.busy || !c?.media_roots.some((r) => r.enabled)}
        >
          ${t("Jetzt einlesen")}
        </button>
      </div>
      ${this.jobs.filter((j) => j.kind === "media" && j.state === "running").map((j) => html`<p class="notice" role="status">${j.progress}/${j.total} ${t("Verzeichnisse geprüft")}</p>`)}
      ${
        c?.media_roots.length
          ? c.media_roots.map(
              (r) =>
                html`<div class="media-root">
                  <div class="row spread">
                    <h3>${r.root_key}</h3>
                    <span class="badge"
                      >${!r.enabled ? t("Deaktiviert") : r.online ? t("Erreichbar") : t("Nicht erreichbar")}</span
                    >
                  </div>
                  <p class="muted small">
                    ${r.path} · ${r.episode_count} ${t("Einträge · Nur lesen")}
                  </p>
                  ${r.error ? html`<p class="error-tag small">${localizeMessage(r.error)}</p>` : nothing}${r.last_scan ? html`<p class="muted small">${t("Zuletzt eingelesen:")} ${new Date(r.last_scan * 1000).toLocaleString(localeTag())}</p>` : nothing}
                </div>`,
            )
          : html`<p class="notice">
              ${t("Keine lokalen Verzeichnisse eingerichtet.")}
            </p>`
      }
      <details class="help-details">
        <summary>${t("Einrichtung und Dateiverwaltung")}</summary>
        <p class="notice">
          ${!c?.mpd_configured ? t("Lokale Dateien werden direkt in diesem Browser abgespielt.") : c?.media_base_url ? html`${t("Medienadresse für MPD:")} ${c.media_base_url}` : t("Für lokale Wiedergabe über MPD MEDIA_BASE_URL auf die für MPD erreichbare PlayPod-Adresse setzen. Browserwiedergabe funktioniert ohne diese Angabe.")}
        </p>
        <p class="muted small">
          ${t("Dateien bleiben beim Entfernen aus dem Katalog auf dem Datenträger. Fehlende Dateien werden beim Einlesen gekennzeichnet.")}
        </p>
      </details>
    </article>
    <details class="settings-section technical-settings">
      <summary>${t("Technik und Verbindungen")}</summary>

      ${[
        ...(c?.mpd_configured
          ? [
              [
                "MPD",
                c.mpd === "connected" ? t("Verbunden") : t("Nicht erreichbar"),
              ],
            ]
          : [[t("Wiedergabe"), t("Nur Browser")]]),
        ["SQLite", t("Bereit")],
        [
          "MQTT",
          c?.mqtt === "connected"
            ? t("Verbunden")
            : c?.mqtt === "disabled"
              ? t("Deaktiviert")
              : t("Nicht verbunden"),
        ],
        ...(!c?.mpd_configured
          ? []
          : [
              [
                t("Titelansage"),
                c?.tts_mode === "audio"
                  ? t("Vor Episode über MPD")
                  : c?.tts === "configured"
                    ? t("Konfiguriert")
                    : t("Deaktiviert"),
              ],
            ]),
      ].map(
        ([a, b]) =>
          html`<div class="service"><span>${a}</span><span>${b}</span></div>`,
      )}
      <p class="muted small" style="margin-top:18px">
        ${t("Feedaktualisierung alle")}
        ${Math.round((c?.rss_interval || 3600) / 60)} ${t("Minuten.")}<br />
        ${c?.rss_last_refresh ? html`${t("Letzte Aktualisierung:")} ${new Date((c.rss_last_refresh.finished || c.rss_last_refresh.created) * 1000).toLocaleString(localeTag())} · ${c.rss_last_refresh.state === "running" ? t("läuft") : c.rss_last_refresh.state === "done" ? (c.rss_last_refresh.errors ? c.rss_last_refresh.errors + t(" Feed(s) fehlgeschlagen") : t("abgeschlossen")) : t("abgebrochen/fehlgeschlagen")}` : t("Noch keine Feedaktualisierung ausgeführt.")}<br />${c?.rss_next_refresh ? html`${t("Nächste automatische Aktualisierung:")} ${new Date(c.rss_next_refresh * 1000).toLocaleString(localeTag())}<br />` : nothing}${c?.rss_scheduler_running === false ? html`<span class="error-tag">${t("Automatische Feedaktualisierung ist nicht aktiv.")}</span><br />` : nothing}${t("Version")}
        ${c?.version || "…"}
      </p>
      <p class="muted small" style="margin-top:18px">
        ${t("Verbindungen werden über Umgebungsvariablen konfiguriert. „Konfiguriert“ bei TTS ist kein Erreichbarkeitstest.")}
      </p>
    </details>
    <details class="settings-section pwa-panel">
      <summary>${t("PlayPod als App")}</summary>
      <p>
        ${t("Über das Browsermenü installieren oder zum Startbildschirm hinzufügen (HTTPS oder localhost).")}
      </p>
    </details>
  </section>`;
}
