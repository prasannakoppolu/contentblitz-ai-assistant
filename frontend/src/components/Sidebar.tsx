import { useEffect, useState } from "react";
import { api } from "../api";
import { initials, relativeTime } from "../settings";
import type { BrandVoice, ThreadSummary, User } from "../types";
import { BrandMark, Icon } from "./Art";

interface Props {
  user: User;
  threads: ThreadSummary[];
  threadId: string;
  onSelectThread: (tid: string) => void;
  onDeleteThread: (tid: string) => void;
  onNewConversation: () => void;
  voice: BrandVoice;
  onVoiceSaved: (v: BrandVoice) => void;
  onSignOut: () => void;
  onOpenAdmin: () => void;
  running: boolean;
  open: boolean;
  onClose: () => void;
}

export function Sidebar(p: Props) {
  return (
    <aside className={`sidebar ${p.open ? "sidebar--open" : ""}`} aria-label="Account and conversations">
      <div className="sidebar__top">
        <p className="sidebar__brand">
          <BrandMark size={24} />
          ContentBlitz
        </p>
        <button type="button" className="icon-btn sidebar__close" onClick={p.onClose} aria-label="Close menu">
          <Icon.X />
        </button>
      </div>

      <button type="button" className="new-chat" onClick={p.onNewConversation} disabled={p.running}>
        <Icon.Plus /> New conversation
      </button>

      <nav className="threads" aria-label="Recent conversations">
        <h2 className="side-heading">Recent</h2>
        {p.threads.length === 0 ? (
          <p className="side-empty">Your conversations appear here once you send a message.</p>
        ) : (
          <ul>
            {p.threads.map((t) => (
              <li key={t.thread_id} className={`thread ${t.thread_id === p.threadId ? "thread--active" : ""}`}>
                <button
                  type="button"
                  className="thread__open"
                  aria-current={t.thread_id === p.threadId ? "page" : undefined}
                  disabled={p.running}
                  onClick={() => p.onSelectThread(t.thread_id)}
                >
                  <span className="thread__title">{t.title || "New conversation"}</span>
                  <span className="thread__when">{relativeTime(t.updated_at)}</span>
                </button>
                <button
                  type="button"
                  className="thread__delete"
                  aria-label={`Remove "${t.title || "New conversation"}" from the list`}
                  disabled={p.running}
                  onClick={() => p.onDeleteThread(t.thread_id)}
                >
                  <Icon.X size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </nav>

      <details className="side-group">
        <summary>
          <Icon.Voice /> Brand voice
        </summary>
        <VoiceEditor threadId={p.threadId} voice={p.voice} onSaved={p.onVoiceSaved} />
      </details>

      <div className="account" aria-label="Signed in as">
        <span className="account__avatar" aria-hidden="true">{initials(p.user.name)}</span>
        <span className="account__who">
          <strong className="account__name">{p.user.name}</strong>
          <span className="account__email">{p.user.email}</span>
        </span>
      </div>
      <div className="sidebar__foot">
        {p.user.is_admin && (
          <a
            className="side-link"
            href="/admin"
            onClick={(e) => {
              e.preventDefault();
              p.onOpenAdmin();
            }}
          >
            <Icon.Gauge /> Admin dashboard
          </a>
        )}
        <button type="button" className="side-link" onClick={p.onSignOut}>
          <Icon.Logout /> Sign out
        </button>
      </div>
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
        className="btn btn--pill"
        disabled={!threadId}
        onClick={() => save({ ...draft, banned_phrases: draft.banned_phrases.map((s) => s.trim()).filter(Boolean) }, "Brand voice saved for this conversation.")}
      >
        Save voice
      </button>
      <label className="field">
        <span>Or paste 1–3 samples of your writing</span>
        <textarea rows={4} value={samples} onChange={(e) => setSamples(e.target.value)} />
      </label>
      <button type="button" className="btn btn--pill" disabled={!samples.trim() || !threadId} onClick={learn}>
        Learn voice from samples
      </button>
      {msg && <p className="small" role="status">{msg}</p>}
    </div>
  );
}
