import { t, localeTag } from "./i18n";
import { html } from "lit";
export const fmt = (value: number) => {
  const s = Math.max(0, Math.floor(value || 0));
  return s >= 3600
    ? `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`
    : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
export const date = (stamp: number | null) =>
  stamp
    ? new Date(stamp * 1000).toLocaleDateString(localeTag(), {
        day: "numeric",
        month: "short",
      })
    : t("Ohne Datum");
export const icon = (name: string) => {
  const paths: Record<string, string> = {
    play: "m9 5 11 7-11 7Z",
    pause: "M8 5v14m8-14v14",
    next: "m5 5 10 7-10 7Zm13 0v14",
    back: "M4 9a8 8 0 1 1 0 7m0-12v5h5",
    forward: "M20 9a8 8 0 1 0 0 7m0-12v5h-5",
    bookmark: "M6 4h12v17l-6-4-6 4Z",
    player: "M4 4h16v16H4Zm6 4 6 4-6 4Z",
    library: "M4 4v16m5-16v16m5-16v16m4-15 3 14",
    activity: "M4 5h16M4 12h16M4 19h16M8 3v4m0 3v4m0 3v4",
    config: "M4 7h16M4 17h16M9 4v6m7 4v6",
    plus: "M12 5v14M5 12h14",
    up: "m6 14 6-6 6 6",
    down: "m6 10 6 6 6-6",
    close: "m6 6 12 12M6 18 18 6",
    star: "m12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1Z",
    speaker: "M4 9h4l5-4v14l-5-4H4Zm13-1a6 6 0 0 1 0 8",
    moon: "M20 14a8 8 0 0 1-10-10 8 8 0 1 0 10 10Z",
    more: "M5 12h.01M12 12h.01M19 12h.01",
    refresh: "M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12 0m0 10a7 7 0 0 1-12 0",
    logo: "M5 8v8m5-12v16m5-13v10m5-7v4",
  };
  return html`<svg viewBox="0 0 24 24" aria-hidden="true">
    <path d=${paths[name] || paths.play}></path>
  </svg>`;
};
