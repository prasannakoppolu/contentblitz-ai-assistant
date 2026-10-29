import type { Quality as Q } from "../types";

const ACRONYMS: Record<string, string> = { seo: "SEO" };
const label = (k: string) => ACRONYMS[k] ?? k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function QualityPanel({ quality, title = "Quality" }: { quality: Q; title?: string }) {
  const tone = quality.score >= 80 ? "good" : quality.score >= 65 ? "fair" : "poor";
  return (
    <section className={`quality quality--${tone}`} aria-label={`${title} score`}>
      <div className="quality__score">
        <span className="quality__num">{quality.score}</span>
        <span className="quality__of">/100 · grade {quality.grade}</span>
      </div>
      <dl className="quality__dims">
        {Object.entries(quality.dimensions).map(([k, v]) => (
          <div key={k} className="dim">
            <dt>{label(k)}</dt>
            <dd>
              <span className="dim__track">
                <span className="dim__bar" style={{ width: `${Math.max(2, Math.min(100, v))}%` }} />
              </span>
              <span className="dim__val">{v}</span>
            </dd>
          </div>
        ))}
      </dl>
      {quality.suggestions.length > 0 && (
        <details className="quality__tips">
          <summary>
            {quality.suggestions.length} suggestion{quality.suggestions.length > 1 ? "s" : ""} to improve
          </summary>
          <ul>
            {quality.suggestions.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function Stat({ value, label: l, hint }: { value: string | number; label: string; hint?: string }) {
  return (
    <div className="stat" title={hint}>
      <span className="stat__value">{value}</span>
      <span className="stat__label">{l}</span>
    </div>
  );
}
