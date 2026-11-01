import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, createSSEParser, setUnauthorizedHandler, streamChat } from "../api";

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
    const final = await streamChat("t", "hi", (e) => seen.push(e.event));
    expect(seen).toEqual(["start", "node", "done"]);
    expect(final.thread_id).toBe("t");
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/api/threads/t/chat");
    expect(JSON.parse(init.body)).toEqual({ message: "hi" });
  });

  it("throws the server's error event", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse(['event: error\ndata: {"message":"boom"}\n\n']));
    await expect(streamChat("t", "hi", () => {})).rejects.toThrow("boom");
  });

  it("throws when the stream ends early", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([]));
    await expect(streamChat("t", "hi", () => {})).rejects.toThrow(/closed before/);
  });

  it("surfaces HTTP validation errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "message too long" }), { status: 422 }),
    );
    await expect(streamChat("t", "x", () => {})).rejects.toThrow("message too long");
  });
});

describe("api errors", () => {
  it("carries the server's error code and extras", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "a@b.co isn't registered", code: "not_registered" }), { status: 404 }),
    );
    const err = (await api.loginStart("a@b.co").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("not_registered");
    expect(err.message).toContain("isn't registered");
  });

  it("signals a lost session so the app can show the sign-in screen", async () => {
    const lost = vi.fn();
    setUnauthorizedHandler(lost);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Please sign in", code: "not_signed_in" }), { status: 401 }),
    );
    await expect(api.threads()).rejects.toThrow("Please sign in");
    expect(lost).toHaveBeenCalledOnce();
    setUnauthorizedHandler(null);
  });

  it("never sends provider settings with chat messages", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('event: done\ndata: {"thread_id":"t","messages":[],"blog_series":[]}\n\n', { status: 200 }),
    );
    await streamChat("t", "hello", () => undefined);
    expect(JSON.parse(String(f.mock.calls[0][1]!.body))).toEqual({ message: "hello" });
  });
});
