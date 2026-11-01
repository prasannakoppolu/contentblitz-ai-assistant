/** Per-viewer conveniences kept in localStorage. Everything that matters lives on the server. */

const threadKey = (userId: number) => `contentblitz.thread.${userId}`;

export function storedThread(userId: number): string | null {
  try {
    return localStorage.getItem(threadKey(userId));
  } catch {
    return null;
  }
}

export function storeThread(userId: number, tid: string): void {
  try {
    localStorage.setItem(threadKey(userId), tid);
  } catch {
    /* storage unavailable: the thread lives for this tab only */
  }
}

export function forgetThread(userId: number): void {
  try {
    localStorage.removeItem(threadKey(userId));
  } catch {
    /* ignore */
  }
}

/** "just now", "5 min ago", "yesterday", "12 Mar" for conversation lists. */
export function relativeTime(epochSeconds: number, now: number = Date.now()): string {
  const diff = Math.max(0, now / 1000 - epochSeconds);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 172800) return "yesterday";
  return new Date(epochSeconds * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}
