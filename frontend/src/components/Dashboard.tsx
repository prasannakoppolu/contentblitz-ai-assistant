import { useEffect, useState } from "react";
import { api } from "../api";
import type { Blog, ConversationState, ImageAsset, LinkedInPost } from "../types";
import { Markdown } from "./Markdown";
import { QualityPanel, Stat } from "./Quality";

type Sub = "blog" | "linkedin" | "image" | "series";

interface Props {
  state: ConversationState;
  onChange: (patch: Partial<ConversationState>) => void;
}

export function Dashboard({ state, onChange }: Props) {
  const available: Sub[] = [
    ...(state.blog ? (["blog"] as Sub[]) : []),
    ...(state.linkedin ? (["linkedin"] as Sub[]) : []),
    ...(state.image ? (["image"] as Sub[]) : []),
    ...(state.blog_series.length > 1 ? (["series"] as Sub[]) : []),
  ];
  const [sub, setSub] = useState<Sub | null>(available[0] ?? null);
  const current = sub && available.includes(sub) ? sub : available[0];

  if (!current) {
    return (
      <div className="empty">
        <h2>Nothing to edit yet</h2>
        <p>Ask for a blog post, LinkedIn post or image in Chat. Each piece appears here for editing and re-scoring.</p>
      </div>
    );
  }
  const names: Record<Sub, string> = { blog: "Blog post", linkedin: "LinkedIn post", image: "Image", series: "Series" };
  return (
    <div className="dashboard">
      <div className="subtabs" role="tablist" aria-label="Content type">
        {available.map((s) => (
          <button key={s} role="tab" aria-selected={s === current} className="subtab" onClick={() => setSub(s)}>
            {names[s]}
          </button>
        ))}
      </div>
      {current === "blog" && state.blog && (
        <BlogEditor tid={state.thread_id} blog={state.blog} onSaved={(blog) => onChange({ blog })} />
      )}
      {current === "linkedin" && state.linkedin && (
        <LinkedInEditor tid={state.thread_id} post={state.linkedin} onSaved={(linkedin) => onChange({ linkedin })} />
      )}
      {current === "image" && state.image && <ImageView image={state.image} />}
      {current === "series" && <SeriesView posts={state.blog_series} />}
    </div>
  );
}

function useSave<T>(fn: () => Promise<T>, onSaved: (v: T) => void) {
  const [status, setStatus] = useState<{ kind: "idle" | "saving" | "saved" | "error"; msg?: string }>({ kind: "idle" });
  const save = async () => {
    setStatus({ kind: "saving" });
    try {
      onSaved(await fn());
      setStatus({ kind: "saved" });
    } catch (e) {
      setStatus({ kind: "error", msg: (e as Error).message });
    }
  };
  return [status, save] as const;
}

function BlogEditor({ tid, blog, onSaved }: { tid: string; blog: Blog; onSaved: (b: Blog) => void }) {
  const [md, setMd] = useState(blog.markdown);
  const [meta, setMeta] = useState(blog.meta_description);
  useEffect(() => {
    setMd(blog.markdown);
    setMeta(blog.meta_description);
  }, [blog.markdown, blog.meta_description]);
  const [status, save] = useSave(() => api.editBlog(tid, md, meta), onSaved);
  const dirty = md !== blog.markdown || meta !== blog.meta_description;

  return (
    <div className="editor">
      <header className="editor__head">
        <h2>{blog.title}</h2>
        <p className="muted">
          Keyword "{blog.primary_keyword}", {blog.template.replace("_", " ")} template, revision {blog.revision}
          {blog.edited_by_human ? " (edited by you)" : ""}, written by {blog.provider}
        </p>
      </header>
      <div className="stats">
        <Stat value={blog.seo.word_count} label="words" />
        <Stat value={`${blog.seo.keyword_density}%`} label="keyword density" hint="Target 1–2%" />
        <Stat value={meta.length} label="meta characters" hint="Target 150–160" />
        <Stat value={blog.seo.readability.flesch_reading_ease} label="reading ease" hint="Flesch; 50–75 is ideal for blogs" />
      </div>
      <QualityPanel quality={blog.quality} />
      <div className="split">
        <div className="split__edit">
          <label className="field">
            <span>Meta description</span>
            <textarea rows={3} value={meta} onChange={(e) => setMeta(e.target.value)} />
          </label>
          <label className="field field--grow">
            <span>Article (Markdown)</span>
            <textarea className="mono" value={md} onChange={(e) => setMd(e.target.value)} />
          </label>
          <SaveBar dirty={dirty} status={status} onSave={save} onReset={() => { setMd(blog.markdown); setMeta(blog.meta_description); }} />
        </div>
        <div className="split__preview page" aria-label="Preview">
          <Markdown className="md md--article">{md}</Markdown>
        </div>
      </div>
      {blog.seo.internal_link_suggestions.length > 0 && (
        <details className="panel-details">
          <summary>Internal link suggestions</summary>
          <ul>
            {blog.seo.internal_link_suggestions.map((l) => (
              <li key={l.anchor_text}>
                Link "{l.anchor_text}" to <code>{l.suggested_url}</code>: {l.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function LinkedInEditor({ tid, post, onSaved }: { tid: string; post: LinkedInPost; onSaved: (p: LinkedInPost) => void }) {
  const [text, setText] = useState(post.text);
  useEffect(() => setText(post.text), [post.text]);
  const [status, save] = useSave(() => api.editLinkedIn(tid, text), onSaved);
  const len = text.length;
  const inRange = len >= 1300 && len <= 1600;
  return (
    <div className="editor">
      <div className="stats">
        <Stat value={len} label="characters" hint="Target 1,300–1,600" />
        <Stat value={post.hashtags.length} label="hashtags" hint="Target 8–12" />
        <Stat value={post.template.replace("_", " ")} label="template" />
      </div>
      <QualityPanel quality={post.quality} />
      <div className="split">
        <div className="split__edit">
          <label className="field field--grow">
            <span>
              Post <em className={inRange ? "ok" : "warn"}>{len} / 1,300–1,600</em>
            </span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <SaveBar dirty={text !== post.text} status={status} onSave={save} onReset={() => setText(post.text)} />
        </div>
        <div className="split__preview">
          <div className="li-card" aria-label="LinkedIn preview">
            <div className="li-card__who">
              <span className="li-card__avatar" aria-hidden="true" />
              <span>
                <strong>You</strong>
                <span className="muted">Preview</span>
              </span>
            </div>
            <p className="li-card__text">{text}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function SaveBar({ dirty, status, onSave, onReset }: {
  dirty: boolean;
  status: { kind: string; msg?: string };
  onSave: () => void;
  onReset: () => void;
}) {
  return (
    <div className="savebar">
      <button type="button" className="btn btn--primary" disabled={!dirty || status.kind === "saving"} onClick={onSave}>
        {status.kind === "saving" ? "Saving…" : "Save and re-score"}
      </button>
      <button type="button" className="btn" disabled={!dirty} onClick={onReset}>
        Discard changes
      </button>
      <span className="savebar__msg" role="status">
        {status.kind === "saved" && !dirty && "Saved and re-scored."}
        {status.kind === "error" && `Couldn't save: ${status.msg}`}
      </span>
    </div>
  );
}

function ImageView({ image }: { image: ImageAsset }) {
  const src = image.src || image.url;
  return (
    <div className="editor">
      {src && <img className="hero-image" src={src} alt={image.alt_text} />}
      {image.provider === "placeholder" && (
        <p className="notice">This is the offline placeholder. Add an OpenAI or Stability key in Settings to generate AI images.</p>
      )}
      <div className="stats">
        <Stat value={image.provider} label="provider" />
        <Stat value={`${image.width}×${image.height}`} label="size" />
        <Stat value={image.format ?? "–"} label="format" />
      </div>
      <QualityPanel quality={image.quality} />
      <h3>Enhanced prompt</h3>
      <p className="prompt">{image.enhanced_prompt}</p>
      {image.attempts && image.attempts.length > 0 && (
        <>
          <h3>Provider attempts</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Result</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {image.attempts.map((a, i) => (
                <tr key={i}>
                  <td>{a.provider}</td>
                  <td className={a.ok ? "ok" : "warn"}>{a.ok ? "Generated" : `Failed: ${a.error ?? "error"}`}</td>
                  <td>{a.latency_s ?? "–"}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function SeriesView({ posts }: { posts: Blog[] }) {
  return (
    <div className="series">
      {posts.map((p, i) => (
        <details key={p.slug + i} className="panel-details">
          <summary>
            Part {i + 1}: {p.title} <span className="muted">({p.quality.score}/100)</span>
          </summary>
          <Markdown className="md md--article">{p.markdown}</Markdown>
        </details>
      ))}
    </div>
  );
}
