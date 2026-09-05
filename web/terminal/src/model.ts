import type { EpisodeResponse, PublicViewKind } from "./api";

export type PanelKind = "inspector" | "health" | "audit" | "help";
export type KeyboardCommand =
  | { kind: "lens"; lens: PublicViewKind }
  | { kind: "next" }
  | { kind: "previous" }
  | { kind: "inspect" }
  | { kind: "escape" }
  | { kind: "filter" }
  | { kind: "panel"; panel: Exclude<PanelKind, "inspector"> }
  | { kind: "refresh" };

export function filterEpisodes(items: readonly EpisodeResponse[], rawQuery: string): EpisodeResponse[] {
  const query = rawQuery.trim().toLocaleLowerCase();
  if (!query) return [...items];
  return items.filter((item) => {
    const searchable = [item.episode_id, ...item.source_ids, ...item.signal_roles]
      .join(" ")
      .toLocaleLowerCase();
    return searchable.includes(query);
  });
}

export function shortId(value: string, width = 10): string {
  if (value.length <= width + 2) return value;
  return `${value.slice(0, width)}…`;
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT"
  );
}

export function resolveKeyboardCommand(
  key: string,
  target: EventTarget | null,
): KeyboardCommand | null {
  if (isEditableTarget(target)) return key === "Escape" ? { kind: "escape" } : null;
  if (key === "1") return { kind: "lens", lens: "RADAR" };
  if (key === "2") return { kind: "lens", lens: "NOW" };
  if (key === "3") return { kind: "lens", lens: "TRENDING" };
  if (key === "j" || key === "ArrowDown") return { kind: "next" };
  if (key === "k" || key === "ArrowUp") return { kind: "previous" };
  if (key === "Enter") return { kind: "inspect" };
  if (key === "Escape") return { kind: "escape" };
  if (key === "/") return { kind: "filter" };
  if (key.toLocaleLowerCase() === "h") return { kind: "panel", panel: "health" };
  if (key.toLocaleLowerCase() === "a") return { kind: "panel", panel: "audit" };
  if (key === "?") return { kind: "panel", panel: "help" };
  if (key.toLocaleLowerCase() === "r") return { kind: "refresh" };
  return null;
}

export function assertSnapshotBinding(expected: string, actual: string, context: string): void {
  if (expected !== actual) {
    throw new Error(`${context} snapshot binding mismatch: expected ${expected}, got ${actual}`);
  }
}

export function displayUnavailable(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "UNAVAILABLE") return "UNAVAILABLE";
  return value;
}
