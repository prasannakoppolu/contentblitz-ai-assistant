import { useEffect, useState } from "react";
import { api } from "../api";
import type { AppConfig, BrandVoice, ClientSettings, Usage } from "../types";

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
  config: AppConfig;
  settings: ClientSettings;
  onSettings: (patch: Partial<ClientSettings>) => void;
  threadId: string;
  voice: BrandVoice;
  onVoiceSaved: (v: BrandVoice) => void;
  usageTick: number;
  onNewConversation: () => void;
  open: boolean;
  onClose: () => void;
}

export function Sidebar(p: Props) {
  const [usage, setUsage] = useState<Usage | null>(null);
  // Refresh after each run or mode switch, not on every keystroke in the key fields.
  const { usageTick, settings } = p;
  useEffect(() => {
    api.usage(settings).then(setUsage).catch(() => setUsage(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usageTick, settings.demo_mode]);

  const setKey = (name: string, value: string) => p.onSettings({ api_keys: { ...p.settings.api_keys, [name]: value } });

  return (
    <aside className={`sidebar ${p.open ? "sidebar--open" : ""}`} aria-label="Settings">
      <div className="sidebar__head">
        <h2>Settings</h2>
        <button type="button" className="btn btn--ghost sidebar__close" onClick={p.onClose} aria-label="Close settings">
          Close
        </button>
      </div>

      <label className="toggle">
        <input
          type="checkbox"
          checked={p.settings.demo_mode}
          onChange={(e) => p.onSettings({ demo_mode: e.target.checked })}
        />
        <span>
          <strong>Offline demo mode</strong>
          <small>Uses built-in sample providers. No API calls, no cost.</small>
        </span>
      </label>
      {p.config.detected_keys.length > 0 && (
        <p className="muted small">Keys found on the server: {p.config.detected_keys.join(", ")}</p>
      )}

      <details className="side-group">
        <summary>API keys</summary>
        <p className="muted small">Kept in this tab's memory only and cleared when you close it.</p>
        {p.config.key_providers.map((k) => (
          <label key={k} className="field">
            <span>{KEY_LABELS[k] ?? k}</span>
            <input
              type="password"
              autoComplete="off"
              value={p.settings.api_keys[k] ?? ""}
              onChange={(e) => setKey(k, e.target.value)}
            />
          </label>
        ))}
      </details>

      <details className="side-group">
        <summary>Providers and quality</summary>
        <label className="field">
          <span>Writing model</span>
          <select value={p.settings.llm_primary} onChange={(e) => p.onSettings({ llm_primary: e.target.value as ClientSettings["llm_primary"] })}>
            <option value="openai">OpenAI GPT-4o</option>
            <option value="anthropic">Claude Sonnet</option>
            <option value="gemini">Gemini Flash</option>
          </select>
        </label>
        <label className="field">
          <span>Research engine</span>
          <select
            value={p.settings.research_primary}
            onChange={(e) => p.onSettings({ research_primary: e.target.value as ClientSettings["research_primary"] })}
          >
            <option value="serpapi">SERP API</option>
            <option value="perplexity">Perplexity</option>
            <option value="tavily">Tavily</option>
          </select>
        </label>
        <label className="field">
          <span>Rewrite blog posts scoring below {p.settings.quality_threshold}</span>
          <input
            type="range"
            min={50}
            max={95}
            value={p.settings.quality_threshold}
            onChange={(e) => p.onSettings({ quality_threshold: Number(e.target.value) })}
          />
        </label>
        <p className="muted small">If a provider fails, the next one takes over automatically.</p>
      </details>

      <details className="side-group">
        <summary>Brand voice</summary>
        <VoiceEditor threadId={p.threadId} voice={p.voice} onSaved={p.onVoiceSaved} />
      </details>

      <details className="side-group" open>
        <summary>Usage since the server started</summary>
        {usage ? (
          <dl className="usage">
            <div><dt>API calls</dt><dd>{usage.calls}</dd></div>
            <div><dt>Estimated cost</dt><dd>${usage.total_cost_usd.toFixed(3)}</dd></div>
            <div><dt>Cache hits</dt><dd>{usage.cache.hits} of {usage.cache.hits + usage.cache.misses}</dd></div>
            <div><dt>Writing chain</dt><dd>{usage.providers.llm?.join(" → ")}</dd></div>
            <div><dt>LangSmith tracing</dt><dd>{p.config.tracing ? "On" : "Off"}</dd></div>
          </dl>
        ) : (
          <p className="muted small">Usage appears after the first request.</p>
        )}
      </details>

      <button type="button" className="btn sidebar__new" onClick={p.onNewConversation}>
        Start a new conversation
      </button>
    </aside>
  );
}

function VoiceEditor({ threadId, voice, onSaved }: { threadId: string; voice: BrandVoice; onSaved: (v: BrandVoice) => void }) {
  const [draft, setDraft] = useState(voice);
  const [samples, setSamples] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => setDraft(voice), [voice]);

  const save = async (v: BrandVoice, done: string) => {
    try {
      onSaved(await api.setVoice(threadId, v));
      setMsg(done);
    } catch (e) {
      setMsg(`Couldn't save the voice: ${(e as Error).message}`);
    }
  };
  const learn = async () => {
    try {
      const learned = await api.learnVoice(samples.split(/\n\s*\n/).filter((s) => s.trim()), draft);
      await save(learned, `Learned tone: ${learned.tone}`);
    } catch (e) {
      setMsg(`Couldn't learn from the samples: ${(e as Error).message}`);
    }
  };
  return (
    <div className="voice">
      <label className="field"><span>Brand name</span><input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
      <label className="field"><span>Tone</span><input value={draft.tone} onChange={(e) => setDraft({ ...draft, tone: e.target.value })} /></label>
      <label className="field"><span>Audience</span><input value={draft.audience} onChange={(e) => setDraft({ ...draft, audience: e.target.value })} /></label>
      <label className="field">
        <span>Phrases to avoid (one per line)</span>
        <textarea
          rows={3}
          value={draft.banned_phrases.join("\n")}
          onChange={(e) => setDraft({ ...draft, banned_phrases: e.target.value.split("\n") })}
        />
      </label>
      <button
        type="button"
        className="btn"
        disabled={!threadId}
        onClick={() => save({ ...draft, banned_phrases: draft.banned_phrases.map((s) => s.trim()).filter(Boolean) }, "Brand voice saved for this conversation.")}
      >
        Save voice
      </button>
      <label className="field">
        <span>Or paste 1–3 samples of your writing</span>
        <textarea rows={4} value={samples} onChange={(e) => setSamples(e.target.value)} />
      </label>
      <button type="button" className="btn" disabled={!samples.trim() || !threadId} onClick={learn}>
        Learn voice from samples
      </button>
      {msg && <p className="small" role="status">{msg}</p>}
    </div>
  );
}
