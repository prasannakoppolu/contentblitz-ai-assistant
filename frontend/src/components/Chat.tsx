import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { ChatMessage, ImageAsset } from "../types";
import { AgentObject, BrandMark, Icon, type AgentKey } from "./Art";
import { Markdown } from "./Markdown";

const EXAMPLE_AGENT: AgentKey[] = ["research", "blog", "linkedin", "image"];

export const EXAMPLES = [
  "Research the latest trends in AI-powered customer service",
  "Write an SEO blog post about remote employee onboarding",
  "Create a LinkedIn post about sustainable packaging",
  "Create a full campaign about B2B podcast marketing",
];

interface Props {
  messages: ChatMessage[];
  running: boolean;
  pending: string | null;
  error: string | null;
  image?: ImageAsset | null;
  onSend: (message: string) => void;
  userName?: string;
  onCopied?: () => void;
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function Chat({ messages, running, pending, error, image, onSend, userName, onCopied }: Props) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const lastImageIdx = messages.map((m) => m.role === "assistant" && m.agents?.includes("image")).lastIndexOf(true);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, pending, running]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || running) return;
    onSend(text);
    setDraft("");
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) submit(e as unknown as FormEvent);
  };

  return (
    <section className="chat" aria-label="Conversation">
      <div className="chat__log" role="log" aria-live="polite">
        {messages.length === 0 && !pending && (
          <div className="chat__empty">
            <BrandMark size={52} className="chat__empty-mark" />
            <h2>{userName ? `Hi ${userName}, what are we making today?` : "What are we making today?"}</h2>
            <p>Ask for research, a blog post, a LinkedIn post or an image. Follow-ups like "make it shorter" edit the last piece.</p>
            <div className="examples">
              {EXAMPLES.map((ex, i) => (
                <button key={ex} type="button" className="example" onClick={() => onSend(ex)} disabled={running}>
                  <span className="example__obj"><AgentObject agent={EXAMPLE_AGENT[i]} size={34} /></span>
                  <span>{ex}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <article key={i} className={`msg msg--${m.role}`}>
            {m.role === "assistant" && (
              <span className="msg__avatar" aria-hidden="true"><BrandMark size={18} /></span>
            )}
            {m.role === "user" ? <p>{m.content}</p> : <Markdown className="md msg__body">{m.content}</Markdown>}
            {m.role === "assistant" && (
              <div className="msg__tools">
                {m.agents && m.agents.length > 0 && <span className="msg__agents">{m.agents.join(", ")}</span>}
                <button
                  type="button"
                  className="chip-btn"
                  onClick={async () => {
                    if (await copyText(m.content)) onCopied?.();
                  }}
                >
                  <Icon.Copy /> Copy reply
                </button>
              </div>
            )}
            {i === lastImageIdx && image?.src && (
              <img className="msg__image" src={image.src} alt={image.alt_text} loading="lazy" />
            )}
          </article>
        ))}
        {pending && (
          <article className="msg msg--user msg--pending">
            <p>{pending}</p>
          </article>
        )}
        {running && (
          <p className="chat__working">
            <span className="msg__avatar msg__avatar--busy" aria-hidden="true"><BrandMark size={18} /></span>
            <span className="dots" aria-hidden="true"><i /><i /><i /></span>
            The agents are working. Progress shows in the pipeline above.
          </p>
        )}
        {error && (
          <p className="chat__error" role="alert">
            {error}
          </p>
        )}
        <div ref={endRef} />
      </div>
      <form className="composer" onSubmit={submit}>
        <label htmlFor="composer-input" className="sr-only">
          Message
        </label>
        <textarea
          id="composer-input"
          rows={1}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask ContentBlitz to research, write a blog or LinkedIn post, make an image…"
        />
        <div className="composer__bar">
          <span className="composer__hint">Shift + Enter adds a new line</span>
          <button
            type="submit"
            className="send-btn"
            aria-label={running ? "Working…" : "Send"}
            disabled={running || !draft.trim()}
          >
            {running ? <span className="spinner" aria-hidden="true" /> : <Icon.ArrowUp />}
          </button>
        </div>
      </form>
    </section>
  );
}
