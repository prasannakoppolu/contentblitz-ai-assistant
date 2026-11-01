import { useEffect, useState } from "react";
import { api } from "../api";
import { relativeTime } from "../settings";
import type { AdminOverview, LLMProvider, ResearchProvider, ServerSettings, User } from "../types";
import { BrandMark } from "./AuthScreen";

const KEY_LABELS: Record<string, string> = {
  openai: "OpenAI (GPT-4o, DALL-E)",
  anthropic: "Anthropic (Claude)",
  gemini: "Google Gemini",
  serpapi: "SERP API",
  perplexity: "Perplexity",
  tavily: "Tavily",
  stability: "Stability AI",
};

interface Props {
  user: User;
  onBack: () => void;
  notify: (text: string) => void;
}

/** Operator-only page: server-wide settings, provider status, usage and accounts. */
export function AdminPage({ user, onBack, notify }: Props) {
  const [data, setData] = useState<AdminOverview | null>(null);
  const [draft, setDraft] = useState<ServerSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () =>
    api
      .adminOverview()
      .then((d) => {
        setData(d);
        setDraft({
          demo_mode: d.effective.demo_mode,
          llm_primary: (d.settings.llm_primary ?? d.fallback_chains.llm?.[0] ?? "openai") as LLMProvider,
          research_primary: (d.settings.research_primary ?? d.fallback_chains.research?.[0] ?? "serpapi") as ResearchProvider,
          quality_threshold: d.effective.quality_threshold,
        });
        setError(null);
      })
      .catch((e) => setError((e as Error).message));
  useEffect(() => {
    void load();
  }, []);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      await api.adminSettings(draft);
      await load();
      notify("Settings saved. New messages use them straight away.");
    } catch (e) {
      notify(`Couldn't save the settings: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="admin">
      <header className="admin__bar">
        <p className="sidebar__brand">
          <BrandMark size={22} />
          ContentBlitz admin
        </p>
        <span className="admin__who muted small">{user.email}</span>
        <button type="button" className="btn" onClick={onBack}>
          Back to workspace
        </button>
      </header>

      <main className="admin__main">
        <h1>Server dashboard</h1>
        <p className="muted">Only accounts listed in ADMIN_EMAILS can see this page. Customers never see these settings.</p>
        {error && <p className="chat__error" role="alert">{error}</p>}
        {!data || !draft ? (
          !error && <p aria-busy="true">Loading…</p>
        ) : (
          <div className="admin__grid">
            <section className="admin__section" aria-labelledby="adm-settings">
              <h2 id="adm-settings">Providers and quality</h2>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={!!draft.demo_mode}
                  onChange={(e) => setDraft({ ...draft, demo_mode: e.target.checked })}
                />
                <span>
                  <strong>Offline mode</strong>
                  <small>Every customer gets built-in sample providers: no API calls, no cost.</small>
                </span>
              </label>
              <label className="field">
                <span>Writing model tried first</span>
                <select value={draft.llm_primary ?? "openai"} onChange={(e) => setDraft({ ...draft, llm_primary: e.target.value as LLMProvider })}>
                  <option value="openai">OpenAI GPT-4o</option>
                  <option value="anthropic">Claude Sonnet</option>
                  <option value="gemini">Gemini Flash</option>
                </select>
              </label>
              <label className="field">
                <span>Research engine tried first</span>
                <select
                  value={draft.research_primary ?? "serpapi"}
                  onChange={(e) => setDraft({ ...draft, research_primary: e.target.value as ResearchProvider })}
                >
                  <option value="serpapi">SERP API</option>
                  <option value="perplexity">Perplexity</option>
                  <option value="tavily">Tavily</option>
                </select>
              </label>
              <label className="field">
                <span>Rewrite blog posts scoring below {draft.quality_threshold}</span>
                <input
                  type="range"
                  min={50}
                  max={95}
                  value={draft.quality_threshold ?? 70}
                  onChange={(e) => setDraft({ ...draft, quality_threshold: Number(e.target.value) })}
                />
              </label>
              <button type="button" className="btn btn--primary" onClick={save} disabled={saving}>
                {saving ? "Saving…" : "Save settings"}
              </button>
            </section>

            <section className="admin__section" aria-labelledby="adm-keys">
              <h2 id="adm-keys">Provider keys</h2>
              <p className="muted small">Keys are read from the server's .env file and never shown in the browser.</p>
              <ul className="keylist">
                {data.key_providers.map((k) => {
                  const on = data.detected_keys.includes(k);
                  return (
                    <li key={k}>
                      <span>{KEY_LABELS[k] ?? k}</span>
                      <span className={on ? "pill pill--on" : "pill"}>{on ? "Configured" : "Not set"}</span>
                    </li>
                  );
                })}
              </ul>
              <dl className="usage">
                <div><dt>Writing chain</dt><dd>{data.usage.providers.llm?.join(" → ")}</dd></div>
                <div><dt>Research chain</dt><dd>{data.usage.providers.research?.join(" → ")}</dd></div>
                <div><dt>Image chain</dt><dd>{data.usage.providers.image?.join(" → ")}</dd></div>
                <div><dt>Sign-in email</dt><dd>{data.email_delivery === "email" ? "SMTP" : "Server log (SMTP not set)"}</dd></div>
                <div><dt>LangSmith tracing</dt><dd>{data.tracing ? "On" : "Off"}</dd></div>
              </dl>
            </section>

            <section className="admin__section" aria-labelledby="adm-usage">
              <h2 id="adm-usage">Usage since the server started</h2>
              <div className="stats">
                <Big value={data.usage.calls} label="API calls" />
                <Big value={data.usage.failures} label="failed attempts" />
                <Big value={`$${data.usage.total_cost_usd.toFixed(3)}`} label="estimated cost" />
                <Big value={data.usage.total_tokens.toLocaleString()} label="tokens" />
                <Big value={`${data.usage.cache.hits}/${data.usage.cache.hits + data.usage.cache.misses}`} label="cache hits" />
              </div>
              <button type="button" className="btn" onClick={() => void load()}>
                Refresh
              </button>
            </section>

            <section className="admin__section admin__section--wide" aria-labelledby="adm-users">
              <h2 id="adm-users">
                Accounts{" "}
                <span className="muted">
                  ({plural(data.totals.users, "person", "people")}, {plural(data.totals.conversations, "conversation")})
                </span>
              </h2>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Email</th>
                      <th>Joined</th>
                      <th>Last sign-in</th>
                      <th>Conversations</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.users.map((u) => (
                      <tr key={u.email}>
                        <td>
                          {u.name}
                          {u.is_admin && <span className="pill pill--on">Admin</span>}
                        </td>
                        <td>{u.email}</td>
                        <td>{relativeTime(u.created_at)}</td>
                        <td>{u.last_login ? relativeTime(u.last_login) : "Never"}</td>
                        <td>{u.conversations}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function Big({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="stat">
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  );
}

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}
