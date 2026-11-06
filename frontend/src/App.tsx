import { useCallback, useEffect, useState } from "react";
import { api, setUnauthorizedHandler, streamChat } from "./api";
import { AdminPage } from "./components/AdminPage";
import { AuthScreen } from "./components/AuthScreen";
import { Chat } from "./components/Chat";
import { Dashboard } from "./components/Dashboard";
import { ExportPanel } from "./components/ExportPanel";
import { ResearchPanel } from "./components/ResearchPanel";
import { Rail, type View } from "./components/Rail";
import { SidePanel, type PanelMode } from "./components/Sidebar";
import { useToast } from "./components/Toast";
import { Icon } from "./components/Art";
import { forgetThread, loadPinned, savePinned, storeThread, storedThread } from "./settings";
import type { AppConfig, ConversationState, ThreadSummary, User } from "./types";

const VIEW_LABEL: Record<View, string> = { chat: "Chat", content: "Content", research: "Research", export: "Export" };

const emptyState = (tid: string): ConversationState => ({ thread_id: tid, messages: [], blog_series: [] });

function usePath() {
  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const go = useCallback((to: string) => {
    if (to !== window.location.pathname) window.history.pushState(null, "", to);
    setPath(to);
  }, []);
  return [path, go] as const;
}

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined = still checking
  const [bootError, setBootError] = useState<string | null>(null);
  const [path, go] = usePath();
  const [toast, notify] = useToast();

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    api.config().then(setConfig).catch((e) => setBootError((e as Error).message));
    api
      .me()
      .then(({ user }) => setUser(user))
      .catch(() => setUser(null));
    return () => setUnauthorizedHandler(null);
  }, []);

  const signOut = async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
      go("/");
    }
  };

  if (bootError) {
    return (
      <main className="boot">
        <h1>ContentBlitz can't reach its server</h1>
        <p>{bootError}. Start the API with <code>uvicorn src.api.server:app --port 8000</code> and reload this page.</p>
      </main>
    );
  }
  if (!config || user === undefined) return <main className="boot" aria-busy="true"><p>Loading ContentBlitz…</p></main>;
  if (!user) {
    return (
      <>
        <AuthScreen
          initialMode={path === "/signup" ? "signup" : "login"}
          onSignedIn={(u) => {
            setUser(u);
            if (path === "/signup" || path === "/login") go("/");
            notify(`Signed in as ${u.name}.`);
          }}
        />
        {toast}
      </>
    );
  }
  if (path === "/admin") {
    return (
      <>
        {user.is_admin ? (
          <AdminPage user={user} onBack={() => go("/")} notify={notify} />
        ) : (
          <main className="boot">
            <h1>This page is for administrators</h1>
            <p>Your account doesn't have access to the admin dashboard.</p>
            <button type="button" className="btn" onClick={() => go("/")}>Back to workspace</button>
          </main>
        )}
        {toast}
      </>
    );
  }
  return (
    <>
      <Workspace key={user.id} config={config} user={user} onSignOut={signOut} onOpenAdmin={() => go("/admin")} notify={notify} />
      {toast}
    </>
  );
}

interface WorkspaceProps {
  config: AppConfig;
  user: User;
  onSignOut: () => void;
  onOpenAdmin: () => void;
  notify: (text: string) => void;
}

function Workspace({ config, user, onSignOut, onOpenAdmin, notify }: WorkspaceProps) {
  const [threadId, setThreadId] = useState<string>("");
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [state, setState] = useState<ConversationState>(() => emptyState(""));
  const [view, setView] = useState<View>("chat");
  const [pinned, setPinned] = useState<boolean>(() => loadPinned());
  const [panel, setPanel] = useState<PanelMode | null>(() => (loadPinned() ? "chats" : null));
  const [running, setRunning] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshThreads = useCallback(() => api.threads().then(({ threads }) => setThreads(threads)).catch(() => undefined), []);

  const open = useCallback(
    (tid: string, st?: ConversationState) => {
      storeThread(user.id, tid);
      setThreadId(tid);
      setState(st ?? emptyState(tid));
      setError(null);
      setPanel((p) => (pinned && p ? p : null));
    },
    [user.id, pinned],
  );

  const newConversation = useCallback(async () => {
    const { thread_id } = await api.newThread();
    open(thread_id);
    void refreshThreads();
  }, [open, refreshThreads]);

  // Restore the last conversation (if it is still ours), otherwise start a fresh one.
  useEffect(() => {
    void refreshThreads();
    const saved = storedThread(user.id);
    if (saved) {
      api
        .state(saved)
        .then((st) => open(saved, st))
        .catch(() => {
          forgetThread(user.id);
          void newConversation();
        });
    } else {
      void newConversation();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.id]);

  const selectThread = async (tid: string) => {
    if (tid === threadId) return setPanel((p) => (pinned ? p : null));
    try {
      open(tid, await api.state(tid));
    } catch (e) {
      notify(`Couldn't open that conversation: ${(e as Error).message}`);
    }
  };

  const deleteThread = async (tid: string) => {
    try {
      await api.deleteThread(tid);
      notify("Conversation removed from your list.");
      if (tid === threadId) await newConversation();
      else void refreshThreads();
    } catch (e) {
      notify(`Couldn't remove it: ${(e as Error).message}`);
    }
  };

  const send = useCallback(
    async (message: string) => {
      if (!threadId || running) return;
      setRunning(true);
      setPending(message);
      setError(null);
      setView("chat");
      try {
        const final = await streamChat(threadId, message, () => undefined);
        setState(final);
      } catch (e) {
        setError(`${(e as Error).message}. Your message wasn't completed; send it again to retry.`);
      } finally {
        setPending(null);
        setRunning(false);
        void refreshThreads();
      }
    },
    [threadId, running, refreshThreads],
  );

  const selectView = (v: View) => {
    if (v === "chat") {
      // Chat toggles the conversations panel, like the reference layout.
      setPanel((p) => (view === "chat" && p === "chats" && !pinned ? null : "chats"));
    } else if (!pinned) {
      setPanel(null);
    } else {
      setPanel("chats");
    }
    setView(v);
  };
  const togglePin = () => {
    const next = !pinned;
    setPinned(next);
    savePinned(next);
    notify(next ? "The chat panel stays open." : "The chat panel hides when you open a page.");
  };

  const counts: Partial<Record<View, number>> = {
    content: [state.blog, state.linkedin, state.image].filter(Boolean).length,
    research: state.research ? state.research.sources.length : 0,
  };
  const current = threads.find((t) => t.thread_id === threadId);
  const title = current?.title || (state.messages.length ? state.topic : "") || "New conversation";
  const firstName = user.name.split(" ")[0];

  return (
    <div className={`app ${panel ? "app--panel" : ""}`}>
      <Rail
        user={user}
        view={view}
        counts={counts}
        voiceOpen={panel === "voice"}
        onSelect={selectView}
        onToggleVoice={() => setPanel((p) => (p === "voice" ? (pinned ? "chats" : null) : "voice"))}
        onOpenAdmin={onOpenAdmin}
        onSignOut={onSignOut}
      />
      {panel && (
        <SidePanel
          mode={panel}
          threads={threads}
          threadId={threadId}
          onSelectThread={selectThread}
          onDeleteThread={deleteThread}
          onNewConversation={() => void newConversation()}
          voice={state.brand_voice ?? config.brand_voice}
          onVoiceSaved={(brand_voice) => {
            setState((s) => ({ ...s, brand_voice }));
            notify("Brand voice saved for this conversation.");
          }}
          running={running}
          pinned={pinned}
          onTogglePin={togglePin}
          onClose={() => setPanel(pinned ? "chats" : null)}
        />
      )}
      {panel && !pinned && <div className="scrim" onClick={() => setPanel(null)} aria-hidden="true" />}
      <main className="main">
        <header className="masthead">
          <button
            type="button"
            className="chats-btn"
            aria-expanded={panel === "chats"}
            onClick={() => setPanel((p) => (p === "chats" ? null : "chats"))}
          >
            <Icon.Menu size={20} />
            <span>Chats</span>
          </button>
          <h1 className="sr-only">
            {VIEW_LABEL[view]}: {title}
          </h1>
        </header>
        <div className="panel">
          {view === "chat" && (
            <Chat
              messages={state.messages}
              running={running}
              pending={pending}
              error={error}
              image={state.image}
              onSend={send}
              userName={firstName}
              onCopied={() => notify("Copied to the clipboard.")}
            />
          )}
          {view === "content" && <Dashboard state={state} onChange={(patch) => setState((s) => ({ ...s, ...patch }))} />}
          {view === "research" && <ResearchPanel state={state} />}
          {view === "export" && <ExportPanel state={state} />}
        </div>
      </main>
    </div>
  );
}
