import { useCallback, useState } from "react";
import type { ClientSettings } from "./types";

const PREFS_KEY = "contentblitz.prefs";
const THREAD_KEY = "contentblitz.thread";

type Prefs = Omit<ClientSettings, "api_keys">;

function readPrefs(): Partial<Prefs> {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
  } catch {
    return {};
  }
}

export function storedThread(): string | null {
  try {
    return localStorage.getItem(THREAD_KEY);
  } catch {
    return null;
  }
}

export function storeThread(tid: string): void {
  try {
    localStorage.setItem(THREAD_KEY, tid);
  } catch {
    /* storage unavailable: thread lives for this tab only */
  }
}

/**
 * Provider preferences persist in localStorage; API keys are deliberately kept in
 * memory only, so they vanish when the tab closes.
 */
export function useSettings(defaults: { demo_mode: boolean; quality_threshold: number }) {
  const [settings, setSettings] = useState<ClientSettings>(() => ({
    demo_mode: defaults.demo_mode,
    llm_primary: "openai",
    research_primary: "serpapi",
    quality_threshold: defaults.quality_threshold,
    ...readPrefs(),
    api_keys: {},
  }));

  const update = useCallback((patch: Partial<ClientSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      const { api_keys: _omit, ...prefs } = next;
      void _omit;
      try {
        localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return [settings, update] as const;
}
