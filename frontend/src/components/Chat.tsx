import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { ChatMessage, ImageAsset } from "../types";
import { Markdown } from "./Markdown";

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
            <h2>{userName ? `What are we making today, ${userName}?` : "What are we making today?"}</h2>
            <p>Ask for research, a blog post, a LinkedIn post or an image. Follow-ups like "make it shorter" edit the last piece.</p>
            <div className="examples">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" className="example" onClick={() => onSend(ex)} disabled={running}>
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <article key={i} className={`msg msg--${m.role}`}>
            {m.role === "user" ? <p>{m.content}</p> : <Markdown>{m.content}</Markdown>}
            {m.role === "assistant" && (
              <div className="msg__tools">
                {m.agents && m.agents.length > 0 && <span className="msg__agents">{m.agents.join(", ")}</span>}
                <button
                  type="button"
                  className="linkish small"
                  onClick={async () => {
                    if (await copyText(m.content)) onCopied?.();
                  }}
                >
                  Copy reply
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
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask for research, a blog post, a LinkedIn post, an image… or refine the last piece"
        />
        <button type="submit" className="btn btn--primary" disabled={running || !draft.trim()}>
          {running ? "Working…" : "Send"}
        </button>
      </form>
    </section>
  );
}
