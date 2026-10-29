import type { TraceEntry } from "../types";

export const STATIONS: { id: string; label: string; does: string }[] = [
  { id: "query_handler", label: "Brief", does: "Reads your request and plans the run" },
  { id: "research", label: "Research", does: "Searches the web and cites sources" },
  { id: "strategist", label: "Strategy", does: "Turns research into a report and brief" },
  { id: "blog", label: "Blog", does: "Writes and optimises the SEO article" },
  { id: "linkedin", label: "LinkedIn", does: "Drafts the post and hashtags" },
  { id: "image", label: "Visual", does: "Generates the image" },
];

export type StationStatus = "idle" | "queued" | "active" | "ok" | "error" | "skipped";

/** Derive each station's status from the plan, the finished trace and what is running now. */
export function stationStatuses(plan: string[], trace: TraceEntry[], running: boolean, active: string | null) {
  const done = new Map(trace.map((t) => [t.agent, t.status] as const));
  const out: Record<string, StationStatus> = {};
  for (const s of STATIONS) {
    const inRun = s.id === "query_handler" ? running || done.has(s.id) : plan.includes(s.id);
    if (active === s.id) out[s.id] = "active";
    else if (done.has(s.id)) out[s.id] = done.get(s.id) as StationStatus;
    else if (inRun && running) out[s.id] = "queued";
    else out[s.id] = "idle";
  }
  return out;
}

export function Pipeline({ statuses, details }: { statuses: Record<string, StationStatus>; details: Record<string, string> }) {
  return (
    <ol className="pipeline" aria-label="Agent pipeline">
      {STATIONS.map((s, i) => {
        const st = statuses[s.id] ?? "idle";
        return (
          <li key={s.id} className={`station station--${st}`} aria-current={st === "active" ? "step" : undefined}>
            <span className="station__num">{i + 1}</span>
            <span className="station__body">
              <span className="station__label">{s.label}</span>
              <span className="station__detail" title={details[s.id] || s.does}>
                {st === "active" ? "Working…" : details[s.id] || s.does}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
