import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { relativeTime } from "../settings";
import type { BrandVoice, ThreadSummary } from "../types";
import { Icon } from "./Art";

export type PanelMode = "chats" | "voice";

interface Props {
  mode: PanelMode;
  threads: ThreadSummary[];
  threadId: string;
  onSelectThread: (tid: string) => void;
  onDeleteThread: (tid: string) => void;
  onNewConversation: () => void;
  voice: BrandVoice;
  onVoiceSaved: (v: BrandVoice) => void;
  running: boolean;
  pinned: boolean;
  onTogglePin: () => void;
  onClose: () => void;
}

/** The panel that slides out next to the rail: conversations, or the brand voice editor. */
export function SidePanel(p: Props) {
  return (
    <aside className="sidepanel" aria-label={p.mode === "chats" ? "Conversations" : "Brand voice"}>
      {p.mode === "chats" ? <Conversations {...p} /> : (
        <>
          <div className="sidepanel__head">
            <h2 className="sidepanel__title">Brand voice</h2>
            <button type="button" className="icon-btn" aria-label="Close panel" onClick={p.onClose}>
              <Icon.X />
            </button>
          </div>
          <VoiceEditor threadId={p.threadId} voice={p.voice} onSaved={p.onVoiceSaved} />
        </>
      )}
    </aside>
  );
}

function Conversations(p: Props) {
  const [query, setQuery] = useState("");
  const [menu, setMenu] = useState(false);
  const menuBox = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const onDoc = (e: MouseEvent) => {
      if (menuBox.current && !menuBox.current.contains(e.target as Node)) setMenu(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenu(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  const q = query.trim().toLowerCase();
  const shown = q ? p.threads.filter((t) => (t.title || "New conversation").toLowerCase().includes(q)) : p.threads;

  return (
    <>
      <div className="sidepanel__head">
        <label className="search-pill">
          <Icon.Search size={17} />
          <span className="sr-only">Search conversations</span>
          <input type="search" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <div className="menu-wrap" ref={menuBox}>
          <button
            type="button"
            className="icon-btn"
            aria-label="Conversation options"
            aria-haspopup="menu"
            aria-expanded={menu}
            onClick={() => setMenu((m) => !m)}
          >
            <Icon.Dots />
          </button>
          {menu && (
            <div className="popover popover--right" role="menu" aria-label="Conversation options">
              <button
                type="button"
                role="menuitemcheckbox"
                aria-checked={p.pinned}
                className="popover__item"
                onClick={() => {
                  p.onTogglePin();
                  setMenu(false);
                }}
              >
                <Icon.Panel /> Keep chat panel visible
                {p.pinned && <Icon.Check size={13} className="popover__check" />}
              </button>
              <hr className="popover__rule" />
              <button
                type="button"
                role="menuitem"
                className="popover__item"
                disabled={p.running}
                onClick={() => {
                  setMenu(false);
                  p.onNewConversation();
                }}
              >
                <Icon.Plus /> New conversation
              </button>
            </div>
          )}
        </div>
      </div>

      {p.threads.length === 0 ? (
        <div className="sidepanel__empty">
          <Icon.Bubble size={30} />
          <h2>Start a conversation</h2>
          <p>Each conversation keeps its research, posts and images together by topic.</p>
          <button type="button" className="btn btn--pill" onClick={p.onNewConversation} disabled={p.running}>
            New conversation
          </button>
        </div>
      ) : (
        <>
          <button type="button" className="new-chat" onClick={p.onNewConversation} disabled={p.running}>
            <Icon.Plus /> New conversation
          </button>
          <nav className="threads" aria-label="Recent conversations">
            <h2 className="side-heading">Recent</h2>
            {shown.length === 0 ? (
              <p className="side-empty">No conversations match "{query}".</p>
            ) : (
              <ul>
                {shown.map((t) => (
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
        </>
      )}
    </>
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
