import { afterEach, describe, expect, it, vi } from "vitest";
import { createSSEParser, streamChat } from "../api";
import type { ClientSettings } from "../types";

const settings: ClientSettings = {
  demo_mode: true,
  api_keys: {},
  llm_primary: "openai",
  research_primary: "serpapi",
  quality_threshold: 70,
};

function sseResponse(chunks: string[]) {
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    start(c) {
      chunks.forEach((ch) => c.enqueue(enc.encode(ch)));
      c.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

afterEach(() => vi.restoreAllMocks());

describe("createSSEParser", () => {
  it("parses events split across chunks", () => {
    const parse = createSSEParser();
    expect(parse('event: node\ndata: {"node":"res')).toEqual([]);
    const out = parse('earch","trace":null}\n\nevent: done\r\ndata: {"thread_id":"t"}\r\n\r\n');
    expect(out).toEqual([
      { event: "node", data: { node: "research", trace: null } },
      { event: "done", data: { thread_id: "t" } },
    ]);
  });
});

describe("streamChat", () => {
  it("reports progress and resolves with the final state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([
        'event: start\ndata: {"thread_id":"t","providers":{},"offline":true}\n\n',
        'event: node\ndata: {"node":"query_handler","trace":null,"plan":["image"]}\n\n',
        'event: done\ndata: {"thread_id":"t","messages":[],"blog_series":[]}\n\n',
      ]),
    );
    const seen: string[] = [];
    const final = await streamChat("t", "hi", settings, (e) => seen.push(e.event));
    expect(seen).toEqual(["start", "node", "done"]);
    expect(final.thread_id).toBe("t");
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/api/threads/t/chat");
    expect(JSON.parse(init.body)).toEqual({ message: "hi", settings });
  });

  it("throws the server's error event", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse(['event: error\ndata: {"message":"boom"}\n\n']));
    await expect(streamChat("t", "hi", settings, () => {})).rejects.toThrow("boom");
  });

  it("throws when the stream ends early", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([]));
    await expect(streamChat("t", "hi", settings, () => {})).rejects.toThrow(/closed before/);
  });

  it("surfaces HTTP validation errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "message too long" }), { status: 422 }),
    );
    await expect(streamChat("t", "x", settings, () => {})).rejects.toThrow("message too long");
  });
});
