import { useCallback, useEffect, useMemo, useState } from "react";
import { api, streamChat } from "./api";
import { Chat } from "./components/Chat";
import { Dashboard } from "./components/Dashboard";
import { ExportPanel } from "./components/ExportPanel";
import { Pipeline, stationStatuses } from "./components/Pipeline";
import { ResearchPanel } from "./components/ResearchPanel";
import { Sidebar } from "./components/Sidebar";
import { storeThread, storedThread, useSettings } from "./settings";
import type { AppConfig, ConversationState, TraceEntry } from "./types";

type Tab = "chat" | "content" | "research" | "export";
const TABS: [Tab, string][] = [
  ["chat", "Chat"],
  ["content", "Content"],
  ["research", "Research"],
  ["export", "Export"],
];

const emptyState = (tid: string): ConversationState => ({ thread_id: tid, messages: [], blog_series: [] });

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setBootError((e as Error).message));
  }, []);

  if (bootError) {
    return (
      <main className="boot">
        <h1>ContentBlitz can't reach its server</h1>
        <p>{bootError}. Start the API with <code>uvicorn src.api.server:app --port 8000</code> and reload this page.</p>
      </main>
    );
  }
  if (!config) return <main className="boot" aria-busy="true"><p>Loading ContentBlitz…</p></main>;
  return <Workspace config={config} />;
}

function Workspace({ config }: { config: AppConfig }) {
  const [settings, updateSettings] = useSettings({ demo_mode: config.default_demo_mode, quality_threshold: config.quality_threshold });
  const [threadId, setThreadId] = useState<string>(() => storedThread() ?? "");
  const [state, setState] = useState<ConversationState>(() => emptyState(threadId));
  const [tab, setTab] = useState<Tab>("chat");
  const [running, setRunning] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<{ plan: string[]; trace: TraceEntry[]; active: string | null }>({ plan: [], trace: [], active: null });
  const [usageTick, setUsageTick] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Create or restore the conversation thread.
  useEffect(() => {
    if (threadId) {
      api.state(threadId).then(setState).catch(() => setState(emptyState(threadId)));
      return;
    }
    api.newThread().then(({ thread_id }) => {
      storeThread(thread_id);
      setThreadId(thread_id);
      setState(emptyState(thread_id));
    });
  }, [threadId]);

  const send = useCallback(
    async (message: string) => {
      if (!threadId || running) return;
      setRunning(true);
      setPending(message);
      setError(null);
      setTab("chat");
      setLive({ plan: [], trace: [], active: "query_handler" });
      try {
        const final = await streamChat(threadId, message, settings, (ev) => {
          if (ev.event !== "node") return;
          setLive((prev) => {
            const plan = ev.data.plan ?? prev.plan;
            const trace = ev.data.trace ? [...prev.trace, ev.data.trace] : prev.trace;
            const doneIds = new Set(trace.map((t) => t.agent));
            const active = ev.data.node === "finalize" ? null : plan.find((a) => !doneIds.has(a)) ?? null;
            return { plan, trace, active };
          });
        });
        setState(final);
      } catch (e) {
        setError(`${(e as Error).message}. Your message wasn't completed; send it again to retry.`);
      } finally {
        setPending(null);
        setRunning(false);
        setLive((prev) => ({ ...prev, active: null }));
        setUsageTick((n) => n + 1);
      }
    },
    [threadId, running, settings],
  );

  const plan = running ? live.plan : state.plan ?? [];
  const trace = running ? live.trace : state.trace ?? [];
  const statuses = useMemo(() => stationStatuses(plan, trace, running, live.active), [plan, trace, running, live.active]);
  const details = useMemo(() => {
    const d: Record<string, string> = Object.fromEntries(trace.map((t) => [t.agent, t.detail]));
    if (d.query_handler !== undefined) {
      const steps = plan.length;
      d.query_handler = steps ? `Planned ${steps} step${steps > 1 ? "s" : ""}` : "Asked what to make";
    }
    return d;
  }, [trace, plan]);

  const counts: Partial<Record<Tab, number>> = {
    content: [state.blog, state.linkedin, state.image].filter(Boolean).length,
    research: state.research ? state.research.sources.length : 0,
  };

  const newConversation = async () => {
    const { thread_id } = await api.newThread();
    storeThread(thread_id);
    setThreadId(thread_id);
    setState(emptyState(thread_id));
    setLive({ plan: [], trace: [], active: null });
    setTab("chat");
    setSidebarOpen(false);
  };

  return (
    <div className="app">
      <Sidebar
        config={config}
        settings={settings}
        onSettings={updateSettings}
        threadId={threadId}
        voice={state.brand_voice ?? config.brand_voice}
        onVoiceSaved={(brand_voice) => setState((s) => ({ ...s, brand_voice }))}
        usageTick={usageTick}
        onNewConversation={newConversation}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      {sidebarOpen && <div className="scrim" onClick={() => setSidebarOpen(false)} aria-hidden="true" />}
      <main className="main">
        <header className="masthead">
          <div className="brand">
            <h1>ContentBlitz</h1>
            <p>Research, blog posts, LinkedIn posts and visuals from one conversation.</p>
          </div>
          <button type="button" className="btn btn--ghost menu-btn" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}>
            Settings
          </button>
        </header>
        {settings.demo_mode && (
          <p className="banner">
            Offline demo mode: content comes from built-in sample providers. Turn it off in Settings and add keys for
            live GPT-4o, Claude, Gemini, web research and DALL-E.
          </p>
        )}
        <Pipeline statuses={statuses} details={details} />
        <nav className="tabs" role="tablist" aria-label="Workspace">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} className="tab" onClick={() => setTab(id)}>
              {label}
              {counts[id] ? <span className="tab__count">{counts[id]}</span> : null}
            </button>
          ))}
        </nav>
        <div className="panel" role="tabpanel">
          {tab === "chat" && (
            <Chat messages={state.messages} running={running} pending={pending} error={error} image={state.image} onSend={send} />
          )}
          {tab === "content" && <Dashboard state={state} onChange={(patch) => setState((s) => ({ ...s, ...patch }))} />}
          {tab === "research" && <ResearchPanel state={state} />}
          {tab === "export" && <ExportPanel state={state} />}
        </div>
      </main>
    </div>
  );
}
