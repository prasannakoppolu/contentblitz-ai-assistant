import { api } from "../api";
import type { ConversationState } from "../types";

const DOC_FORMATS: [string, string][] = [
  ["md", "Markdown"],
  ["html", "HTML"],
  ["txt", "Plain text"],
  ["pdf", "PDF"],
  ["wxr", "WordPress XML"],
];

function Group({ title, note, links }: { title: string; note: string; links: { href: string; label: string }[] }) {
  return (
    <section className="export-group">
      <h3>{title}</h3>
      <p className="muted">{note}</p>
      <div className="export-links">
        {links.map((l) => (
          <a key={l.href} className="btn" href={l.href} download>
            {l.label}
          </a>
        ))}
      </div>
    </section>
  );
}

export function ExportPanel({ state }: { state: ConversationState }) {
  const tid = state.thread_id;
  const { blog, linkedin, image, strategy_report: report, blog_series: series } = state;
  if (!blog && !linkedin && !image && !report) {
    return (
      <div className="empty">
        <h2>Nothing to download yet</h2>
        <p>Content you create in Chat can be downloaded here as Markdown, HTML, PDF, WordPress XML and more.</p>
      </div>
    );
  }
  const doc = (artifact: string) => DOC_FORMATS.map(([f, label]) => ({ href: api.exportUrl(tid, artifact, f), label }));
  return (
    <div className="export">
      {blog && <Group title={blog.title} note="Blog post, ready for your CMS or editor." links={doc("blog")} />}
      {series.length > 1 && (
        <Group
          title={`${series.length}-part series`}
          note="Every part in one WordPress import file, saved as drafts."
          links={[{ href: api.exportUrl(tid, "series", "wxr"), label: "WordPress XML" }]}
        />
      )}
      {linkedin && (
        <Group
          title="LinkedIn post"
          note="Plain text to paste, or JSON for Buffer and Hootsuite."
          links={[
            { href: api.exportUrl(tid, "linkedin", "txt"), label: "Plain text" },
            { href: api.exportUrl(tid, "linkedin", "json"), label: "Scheduler JSON" },
          ]}
        />
      )}
      {image?.src && (
        <Group
          title="Image"
          note={`${image.width}×${image.height} ${image.format ?? ""}`}
          links={[{ href: image.src, label: `Download ${image.format ?? "image"}` }]}
        />
      )}
      {report && <Group title="Research report" note="The strategist's report with sources." links={doc("report")} />}
    </div>
  );
}
