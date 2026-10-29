import type {
  AppConfig,
  Blog,
  BrandVoice,
  ClientSettings,
  ConversationState,
  LinkedInPost,
  StreamEvent,
  Usage,
} from "./types";

const BASE = "/api";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const send = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  config: () => fetch(`${BASE}/config`).then((r) => json<AppConfig>(r)),
  newThread: () => fetch(`${BASE}/threads`, { method: "POST" }).then((r) => json<{ thread_id: string }>(r)),
  state: (tid: string) => fetch(`${BASE}/threads/${tid}/state`).then((r) => json<ConversationState>(r)),
  editBlog: (tid: string, markdown: string, meta_description: string) =>
    fetch(`${BASE}/threads/${tid}/artifacts/blog`, send("PUT", { markdown, meta_description })).then((r) => json<Blog>(r)),
  editLinkedIn: (tid: string, text: string) =>
    fetch(`${BASE}/threads/${tid}/artifacts/linkedin`, send("PUT", { text })).then((r) => json<LinkedInPost>(r)),
  setVoice: (tid: string, voice: BrandVoice) =>
    fetch(`${BASE}/threads/${tid}/brand-voice`, send("PUT", voice)).then((r) => json<BrandVoice>(r)),
  learnVoice: (samples: string[], base?: BrandVoice) =>
    fetch(`${BASE}/brand-voice/learn`, send("POST", { samples, base })).then((r) => json<BrandVoice>(r)),
  usage: (settings: ClientSettings) => fetch(`${BASE}/usage`, send("POST", settings)).then((r) => json<Usage>(r)),
  exportUrl: (tid: string, artifact: string, fmt: string) => `${BASE}/threads/${tid}/export/${artifact}/${fmt}`,
};

/** Incremental Server-Sent Events parser: feed text chunks, get complete events back. */
export function createSSEParser() {
  let buffer = "";
  return (chunk: string): StreamEvent[] => {
    buffer += chunk.replace(/\r\n/g, "\n");
    const events: StreamEvent[] = [];
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) events.push({ event, data: JSON.parse(data.join("\n")) } as StreamEvent);
    }
    return events;
  };
}

/** POST a chat message and stream agent progress. Resolves with the final state. */
export async function streamChat(
  tid: string,
  message: string,
  settings: ClientSettings,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<ConversationState> {
  const res = await fetch(`${BASE}/threads/${tid}/chat`, { ...send("POST", { message, settings }), signal });
  if (!res.ok || !res.body) await json(res);
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  const parse = createSSEParser();
  let final: ConversationState | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const ev of parse(decoder.decode(value, { stream: true }))) {
      onEvent(ev);
      if (ev.event === "done") final = ev.data;
      if (ev.event === "error") throw new Error(ev.data.message);
    }
  }
  if (!final) throw new Error("The connection closed before the reply finished. Try sending the message again.");
  return final;
}
