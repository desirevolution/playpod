import type { PlayerState } from "./types";

type Snapshot = Pick<
  PlayerState,
  "state" | "elapsed" | "duration" | "current" | "timer"
> & { phase?: PlayerState["phase"] };

/** Display only: MPD and the server remain authoritative for all actions. */
export class DisplayClock {
  private snapshot: Snapshot | null = null;
  private at = 0;
  private elapsed = 0;
  private remaining = 0;

  sync(next: Snapshot, now: number, command = false) {
    const previous = this.snapshot;
    const predicted = this.read(now);
    const continuous =
      !command &&
      previous?.state === "play" &&
      next.state === "play" &&
      previous.current?.id === next.current?.id &&
      previous.phase === next.phase &&
      previous.timer.suspended === next.timer.suspended &&
      now - this.at < 5000;
    // MPD samples and browser polls arrive independently. Ignore small sampling
    // differences so a poll cannot make the displayed second jump backwards.
    this.elapsed =
      continuous && Math.abs(predicted.elapsed - next.elapsed) <= 2
        ? predicted.elapsed
        : next.elapsed;
    this.remaining =
      continuous &&
      previous?.timer.enabled === next.timer.enabled &&
      previous?.timer.minutes === next.timer.minutes &&
      Math.abs(predicted.remaining - next.timer.remaining) <= 2
        ? predicted.remaining
        : next.timer.remaining;
    this.snapshot = next;
    this.at = now;
  }

  read(now: number) {
    const s = this.snapshot;
    // Brief outages must not leave an apparently live player counting forever.
    const delta =
      s?.state === "play"
        ? Math.max(0, Math.min(5000, now - this.at)) / 1000
        : 0;
    return {
      elapsed: Math.max(
        0,
        Math.min(
          s?.duration || Infinity,
          this.elapsed + (s?.phase === "announcement" ? 0 : delta),
        ),
      ),
      remaining: s?.timer.enabled
        ? Math.max(
            0,
            this.remaining -
              (s?.timer.suspended ||
              (s?.phase === "announcement" && !s.timer.run_active)
                ? 0
                : delta),
          )
        : 0,
    };
  }
}
