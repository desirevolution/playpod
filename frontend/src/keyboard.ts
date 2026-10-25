export type Shortcut =
  | "player"
  | "toggle"
  | "rewind"
  | "forward"
  | "next"
  | "volume-up"
  | "volume-down";

export function shortcut(
  e: Pick<
    KeyboardEvent,
    | "key"
    | "code"
    | "ctrlKey"
    | "metaKey"
    | "altKey"
    | "shiftKey"
    | "repeat"
    | "isComposing"
    | "defaultPrevented"
  >,
  editing: boolean,
  interactive: boolean,
  dialog: boolean,
): Shortcut | null {
  if (
    e.defaultPrevented ||
    e.isComposing ||
    e.ctrlKey ||
    e.metaKey ||
    e.altKey ||
    e.shiftKey ||
    editing ||
    dialog
  )
    return null;
  if (e.key.toLowerCase() === "p") return e.repeat ? null : "player";
  if (interactive) return null;
  if (e.code === "ArrowUp") return "volume-up";
  if (e.code === "ArrowDown") return "volume-down";
  if (e.repeat) return null;
  return (
    ({ Space: "toggle", ArrowLeft: "rewind", ArrowRight: "forward" } as const)[
      e.code as "Space" | "ArrowLeft" | "ArrowRight"
    ] ?? (e.key.toLowerCase() === "n" ? "next" : null)
  );
}
