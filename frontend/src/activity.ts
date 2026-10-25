import type { ActivityEvent } from "./types";

export function managementLink(event: ActivityEvent) {
  return event.episode_id
    ? `#management/episodes/${event.episode_id}`
    : event.kind === "feed_added" && event.feed_id
      ? `#management/feeds/${event.feed_id}`
      : null;
}

export function managementTarget(hash: string) {
  const match = /^#management\/(episodes|feeds)\/([1-9]\d*)$/.exec(hash);
  if (!match || !Number.isSafeInteger(Number(match[2]))) return null;
  return { kind: match[1], id: Number(match[2]) };
}

export function groupActivity(events: ActivityEvent[]) {
  const groups: { day: Date; items: ActivityEvent[] }[] = [];
  for (const event of events) {
    const date = new Date(event.created * 1000);
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    let group = groups.at(-1);
    if (!group || group.day.getTime() !== day.getTime()) {
      group = { day, items: [] };
      groups.push(group);
    }
    group.items.push(event);
  }
  return groups;
}
