import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Chat } from "../components/Chat";
import { Dashboard } from "../components/Dashboard";
import { ExportPanel } from "../components/ExportPanel";
import { Pipeline, stationStatuses } from "../components/Pipeline";
import { ResearchPanel } from "../components/ResearchPanel";
import type { Blog, ConversationState, Quality } from "../types";

const quality: Quality = {
  content_type: "blog",
  score: 88,
  grade: "B",
  dimensions: { seo: 82, readability: 100 },
  suggestions: ["Add one more statistic"],
};

const blog: Blog = {
  title: "Hybrid Work: A Practical Guide",
  slug: "hybrid-work",
  markdown: "# Hybrid Work: A Practical Guide\n\nHello **world**.",
  meta_description: "m".repeat(150),
  primary_keyword: "hybrid work",
  secondary_keywords: ["hybrid work tools"],
  template: "how_to",
  word_count: 900,
  seo: {
    keyword_density: 1.5,
    word_count: 900,
    meta_length: 150,
    h1_count: 1,
    h2_count: 4,
    readability: { flesch_reading_ease: 60, flesch_kincaid_grade: 8 },
    internal_link_suggestions: [],
    issues: [],
  },
  quality,
  provider: "mock",
  revision: 1,
};

const baseState = (patch: Partial<ConversationState> = {}): ConversationState => ({
  thread_id: "t1",
  messages: [],
  blog_series: [],
  ...patch,
});

afterEach(() => vi.restoreAllMocks());

describe("Chat", () => {
  it("offers examples when empty and sends one on click", async () => {
    const onSend = vi.fn();
    render(<Chat messages={[]} running={false} pending={null} error={null} onSend={onSend} />);
    await userEvent.click(screen.getByRole("button", { name: /full campaign/ }));
    expect(onSend).toHaveBeenCalledWith("Create a full campaign about B2B podcast marketing");
  });

  it("sends on Enter, not on Shift+Enter, and blocks while running", async () => {
    const onSend = vi.fn();
    const { rerender } = render(<Chat messages={[]} running={false} pending={null} error={null} onSend={onSend} />);
    const box = screen.getByLabelText("Message");
    await userEvent.type(box, "Research AI{Shift>}{Enter}{/Shift}more");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, "{Enter}");
    expect(onSend).toHaveBeenCalledWith("Research AI\nmore");
    rerender(<Chat messages={[]} running pending="Research AI" error={null} onSend={onSend} />);
    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
  });

  it("renders markdown replies, errors and the generated image", () => {
    render(
      <Chat
        messages={[
          { role: "user", content: "make an image" },
          { role: "assistant", content: "**Image generated**", agents: ["image"] },
        ]}
        running={false}
        pending={null}
        error="Network down"
        image={{ src: "/api/images/x.png", alt_text: "Illustration: bees" } as never}
        onSend={() => {}}
      />,
    );
    expect(screen.getByText("Image generated").tagName).toBe("STRONG");
    expect(screen.getByRole("alert")).toHaveTextContent("Network down");
    expect(screen.getByAltText("Illustration: bees")).toHaveAttribute("src", "/api/images/x.png");
  });
});

describe("Pipeline", () => {
  it("derives station statuses from plan, trace and activity", () => {
    const st = stationStatuses(
      ["research", "blog", "image"],
      [
        { agent: "query_handler", status: "ok", detail: "" },
        { agent: "research", status: "error", detail: "" },
      ],
      true,
      "blog",
    );
    expect(st).toMatchObject({ query_handler: "ok", research: "error", blog: "active", image: "queued", linkedin: "idle" });
  });

  it("marks the active station for assistive tech", () => {
    render(<Pipeline statuses={{ research: "active" }} details={{}} />);
    const active = screen.getByText("Research").closest("li");
    expect(active).toHaveAttribute("aria-current", "step");
    expect(active).toHaveTextContent("Working…");
  });
});

describe("Dashboard", () => {
  it("shows an empty state", () => {
    render(<Dashboard state={baseState()} onChange={() => {}} />);
    expect(screen.getByText("Nothing to edit yet")).toBeInTheDocument();
  });

  it("edits, saves and re-scores the blog post", async () => {
    const saved = { ...blog, markdown: "# New", revision: 2, quality: { ...quality, score: 40 } };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(saved)));
    const onChange = vi.fn();
    render(<Dashboard state={baseState({ blog })} onChange={onChange} />);
    expect(screen.getByText("SEO")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save and re-score" });
    expect(save).toBeDisabled();
    const article = screen.getByLabelText("Article (Markdown)");
    await userEvent.clear(article);
    await userEvent.type(article, "# New");
    await userEvent.click(save);
    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ blog: saved }));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/threads/t1/artifacts/blog");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string).markdown).toBe("# New");
  });

  it("reports a failed save", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "No blog" }), { status: 404 }));
    render(<Dashboard state={baseState({ blog })} onChange={() => {}} />);
    await userEvent.type(screen.getByLabelText("Meta description"), "!");
    await userEvent.click(screen.getByRole("button", { name: "Save and re-score" }));
    expect(await screen.findByText("Couldn't save: No blog")).toBeInTheDocument();
  });

  it("switches between content types", async () => {
    const linkedin = { text: "Post text #A", hashtags: ["#A"], template: "tips", char_count: 12, quality, provider: "mock", revision: 1 };
    render(<Dashboard state={baseState({ blog, linkedin })} onChange={() => {}} />);
    await userEvent.click(screen.getByRole("tab", { name: "LinkedIn post" }));
    expect(screen.getByLabelText("LinkedIn preview")).toHaveTextContent("Post text #A");
  });
});

describe("ResearchPanel", () => {
  it("links citations to numbered sources", () => {
    const research = {
      topic: "bees",
      summary: "Summary",
      key_findings: ["Bees are busy [1]."],
      statistics: [],
      trends: [],
      audience_insights: [],
      content_angles: [],
      keywords: ["bees"],
      sources: [{ title: "Bee source", url: "https://bees.example" }],
      search_providers: ["serpapi"],
      analysis_provider: "openai",
      quality,
    };
    render(<ResearchPanel state={baseState({ research })} />);
    expect(screen.getByRole("link", { name: "1" })).toHaveAttribute("href", "#src-1");
    expect(screen.getByRole("link", { name: "Bee source" })).toHaveAttribute("href", "https://bees.example");
  });
});

describe("ExportPanel", () => {
  it("links every format to the export endpoint", () => {
    render(<ExportPanel state={baseState({ blog, blog_series: [blog, { ...blog, slug: "b2" }] })} />);
    expect(screen.getAllByRole("link", { name: "PDF" })[0]).toHaveAttribute("href", "/api/threads/t1/export/blog/pdf");
    expect(screen.getAllByRole("link", { name: "WordPress XML" }).map((a) => a.getAttribute("href"))).toContain(
      "/api/threads/t1/export/series/wxr",
    );
  });
});
