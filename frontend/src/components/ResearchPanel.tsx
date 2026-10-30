import type { ClaimCheck, ClaimStatus, ConversationState } from "../types";
import { Markdown } from "./Markdown";
import { QualityPanel, Stat } from "./Quality";

const SECTIONS: [string, keyof NonNullable<ConversationState["research"]>][] = [
  ["Key findings", "key_findings"],
  ["By the numbers", "statistics"],
  ["Trends", "trends"],
  ["Audience insights", "audience_insights"],
  ["Content angles", "content_angles"],
];

/** Render "[n]" citations as superscript links to the numbered source. */
function Cited({ text }: { text: string }) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d+)\]$/);
        return m ? (
          <sup key={i}>
            <a href={`#src-${m[1]}`} className="cite">
              {m[1]}
            </a>
          </sup>
        ) : (
          <span key={i}>{p}</span>
        );
      })}
    </>
  );
}

const STATUS_LABEL: Record<ClaimStatus, string> = {
  supported: "Supported by source",
  weak: "Loosely supported",
  unverified: "Figure not found in source",
  uncited: "No citation",
  invalid_citation: "Broken citation",
};

function ClaimBadge({ check }: { check?: ClaimCheck }) {
  if (!check) return null;
  return (
    <span className={`claim claim--${check.status}`} title={check.note}>
      {STATUS_LABEL[check.status]}
    </span>
  );
}

export function ResearchPanel({ state }: { state: ConversationState }) {
  const r = state.research;
  const v = r?.verification?.summary;
  const checks = new Map((r?.verification?.claims ?? []).map((c) => [c.claim, c]));
  if (!r) {
    return (
      <div className="empty">
        <h2>No research yet</h2>
        <p>Try "Research trends in creator marketing". Findings, statistics and every source appear here.</p>
      </div>
    );
  }
  return (
    <div className="research">
      <header className="editor__head">
        <h2>{r.topic}</h2>
        <p className="muted">
          Searched with {r.search_providers.join(", ") || "–"}, analysed by {r.analysis_provider}
        </p>
      </header>
      {r.offline_demo && (
        <p className="notice">These are offline demo sources for illustration. Add a SERP API, Perplexity or Tavily key for live research.</p>
      )}
      <div className="stats">
        <Stat value={r.sources.length} label="sources" />
        <Stat value={r.key_findings.length} label="findings" />
        <Stat value={r.statistics.length} label="statistics" />
        {v && <Stat value={`${v.supported}/${v.claims_checked}`} label="claims verified" hint="Claims whose cited source covers them" />}
        {v && <Stat value={v.avg_source_credibility} label="avg source credibility" hint="0-100, by publisher type and recency" />}
      </div>
      {v && v.needs_review > 0 && (
        <p className="notice">
          {v.needs_review} claim{v.needs_review > 1 ? "s aren't" : " isn't"} confirmed by the cited source's snippet. Check
          the flagged items against the full source before publishing.
        </p>
      )}
      <QualityPanel quality={r.quality} title="Research quality" />
      <div className="research__cols">
        <div className="research__main">
          <h3>Summary</h3>
          <p className="lede">{r.summary}</p>
          {SECTIONS.map(([title, key]) => {
            const items = (r[key] as string[]) || [];
            return items.length ? (
              <section key={key}>
                <h3>{title}</h3>
                <ul>
                  {items.map((x) => (
                    <li key={x}>
                      <Cited text={x} /> <ClaimBadge check={checks.get(x)} />
                    </li>
                  ))}
                </ul>
              </section>
            ) : null;
          })}
          {r.keywords.length > 0 && (
            <section>
              <h3>Keyword ideas</h3>
              <ul className="chips">
                {r.keywords.map((k) => (
                  <li key={k} className="chip">
                    {k}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
        <aside className="research__sources" aria-label="Sources">
          <h3>Sources</h3>
          <ol>
            {r.sources.map((s, i) => (
              <li key={s.url} id={`src-${i + 1}`}>
                <a href={s.url} target="_blank" rel="noreferrer">
                  {s.title}
                </a>
                {s.credibility && (
                  <span className={`cred cred--${s.credibility.tier}`} title={s.credibility.reasons.join("; ")}>
                    {s.credibility.tier} credibility · {s.credibility.score}
                  </span>
                )}
                {s.snippet && <p className="muted">{s.snippet.slice(0, 220)}</p>}
              </li>
            ))}
          </ol>
        </aside>
      </div>
      {state.strategy_report && (
        <details className="panel-details">
          <summary>Full strategy report</summary>
          <Markdown className="md md--article">{state.strategy_report}</Markdown>
        </details>
      )}
    </div>
  );
}
