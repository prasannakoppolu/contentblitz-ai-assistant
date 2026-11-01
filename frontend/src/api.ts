import type {
  AdminOverview,
  AppConfig,
  Blog,
  BrandVoice,
  CodeSent,
  ConversationState,
  LinkedInPost,
  ServerSettings,
  StreamEvent,
  ThreadSummary,
  User,
} from "./types";

const BASE = "/api";

/** An API failure with the server's machine-readable code (e.g. "not_registered"). */
export class ApiError extends Error {
  status: number;
  code?: string;
  extra: Record<string, unknown>;
  constructor(message: string, status: number, code?: string, extra: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

/** Called when any request comes back 401, so the app can return to the sign-in screen. */
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    let code: string | undefined;
    let extra: Record<string, unknown> = {};
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      if (body?.code) {
        const { detail: _d, code: c, ...rest } = body;
        void _d;
        code = c;
        extra = rest;
      }
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && code === "not_signed_in") onUnauthorized?.();
    throw new ApiError(detail, res.status, code, extra);
  }
  return res.json() as Promise<T>;
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  credentials: "same-origin",
  headers: body === undefined ? undefined : { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});
const get = (url: string) => fetch(url, { credentials: "same-origin" });

export const api = {
  config: () => get(`${BASE}/config`).then((r) => json<AppConfig>(r)),

  // --- auth ---
  me: () => get(`${BASE}/auth/me`).then((r) => json<{ user: User }>(r)),
  loginStart: (email: string) => fetch(`${BASE}/auth/login/start`, send("POST", { email })).then((r) => json<CodeSent>(r)),
  signupStart: (email: string, name: string) =>
    fetch(`${BASE}/auth/signup/start`, send("POST", { email, name })).then((r) => json<CodeSent>(r)),
  verify: (email: string, code: string, purpose: "login" | "signup") =>
    fetch(`${BASE}/auth/verify`, send("POST", { email, code, purpose })).then((r) => json<{ user: User }>(r)),
  logout: () => fetch(`${BASE}/auth/logout`, send("POST")).then((r) => json<{ ok: boolean }>(r)),

  // --- conversations ---
  threads: () => get(`${BASE}/threads`).then((r) => json<{ threads: ThreadSummary[] }>(r)),
  newThread: () => fetch(`${BASE}/threads`, send("POST")).then((r) => json<{ thread_id: string }>(r)),
  renameThread: (tid: string, title: string) =>
    fetch(`${BASE}/threads/${tid}`, send("PATCH", { title })).then((r) => json<{ title: string }>(r)),
  deleteThread: (tid: string) => fetch(`${BASE}/threads/${tid}`, send("DELETE")).then((r) => json<{ ok: boolean }>(r)),
  state: (tid: string) => get(`${BASE}/threads/${tid}/state`).then((r) => json<ConversationState>(r)),
  editBlog: (tid: string, markdown: string, meta_description: string) =>
    fetch(`${BASE}/threads/${tid}/artifacts/blog`, send("PUT", { markdown, meta_description })).then((r) => json<Blog>(r)),
  editLinkedIn: (tid: string, text: string) =>
    fetch(`${BASE}/threads/${tid}/artifacts/linkedin`, send("PUT", { text })).then((r) => json<LinkedInPost>(r)),
  setVoice: (tid: string, voice: BrandVoice) =>
    fetch(`${BASE}/threads/${tid}/brand-voice`, send("PUT", voice)).then((r) => json<BrandVoice>(r)),
  learnVoice: (samples: string[], base?: BrandVoice) =>
    fetch(`${BASE}/brand-voice/learn`, send("POST", { samples, base })).then((r) => json<BrandVoice>(r)),
  exportUrl: (tid: string, artifact: string, fmt: string) => `${BASE}/threads/${tid}/export/${artifact}/${fmt}`,

  // --- admin ---
  adminOverview: () => get(`${BASE}/admin/overview`).then((r) => json<AdminOverview>(r)),
  adminSettings: (s: ServerSettings) =>
    fetch(`${BASE}/admin/settings`, send("PUT", s)).then((r) => json<{ settings: ServerSettings }>(r)),
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
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<ConversationState> {
  const res = await fetch(`${BASE}/threads/${tid}/chat`, { ...send("POST", { message }), signal });
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
