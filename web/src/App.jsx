import { useEffect, useMemo, useRef, useState } from "react";
import {
  chatStream, getAuth, logout,
  listConversations, getConversation, deleteConversation, closeConversation,
} from "./api.js";
import Auth from "./components/Auth.jsx";
import Masthead from "./components/Masthead.jsx";
import EmptyState from "./components/EmptyState.jsx";
import Composer from "./components/Composer.jsx";
import Exchange from "./components/Exchange.jsx";
import ConversationList from "./components/ConversationList.jsx";

function newThreadId() {
  return `web-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function App() {
  const [exchanges, setExchanges] = useState([]);
  const [busy, setBusy] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [threadId, setThreadId] = useState(newThreadId);
  const [auth, setAuth] = useState(getAuth);
  const [authOpen, setAuthOpen] = useState(false);
  const [conversations, setConversations] = useState([]);
  const threadRef = useRef(threadId);
  const thinkingRef = useRef(thinking);
  const bottomRef = useRef(null);

  useEffect(() => {
    thinkingRef.current = thinking;
  }, [thinking]);

  useEffect(() => {
    threadRef.current = threadId;
  }, [threadId]);

  // Keep the latest exchange in view as it arrives.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [exchanges]);

  const taxYear = useMemo(() => {
    const last = [...exchanges].reverse().find((e) => e.income_year);
    return last?.income_year ?? null;
  }, [exchanges]);

  async function refreshConversations() {
    if (!getAuth()) { setConversations([]); return; }
    try { setConversations(await listConversations()); } catch { /* ignore */ }
  }
  useEffect(() => { refreshConversations(); }, [auth]);

  function patch(id, fields) {
    setExchanges((prev) => prev.map((e) => (e.id === id ? { ...e, ...fields } : e)));
  }

  async function send(question) {
    const id = newThreadId();
    setExchanges((prev) => [
      ...prev,
      { id, question, status: "pending", stage: "", streamText: "" },
    ]);
    setBusy(true);
    await chatStream(
      question,
      threadRef.current,
      {
        onStage: (label) => patch(id, { stage: label }),
        onToken: (text) =>
          setExchanges((prev) =>
            prev.map((e) =>
              e.id === id
                ? { ...e, status: "streaming", streamText: (e.streamText || "") + text }
                : e
            )
          ),
        onDone: (data) => patch(id, { status: "done", ...data }),
        onError: (err) => patch(id, { status: "error", error: err.message }),
      },
      { reasoning: thinkingRef.current }
    );
    setBusy(false);
    refreshConversations();
  }

  function closeCurrentChat() {
    if (!getAuth() || exchanges.length === 0) return;
    closeConversation(threadRef.current).catch(() => { /* ignore */ });
  }

  function newChat() {
    closeCurrentChat();
    setExchanges([]);
    setThreadId(newThreadId());
  }

  async function openConversation(tid) {
    try {
      const data = await getConversation(tid);
      const ex = [];
      const msgs = data.messages || [];
      for (let i = 0; i < msgs.length; i++) {
        if (msgs[i].role === "user") {
          const ans = msgs[i + 1] && msgs[i + 1].role === "assistant" ? msgs[i + 1].content : "";
          ex.push({ id: `${tid}-${i}`, question: msgs[i].content, status: "done",
                    answer: ans, citations: [], related_links: [], suggestions: [] });
        }
      }
      setThreadId(tid);
      setExchanges(ex);
    } catch { /* ignore */ }
  }

  async function removeConversation(tid) {
    try { await deleteConversation(tid); } catch { /* ignore */ }
    setConversations((prev) => prev.filter((c) => c.thread_id !== tid));
    if (tid === threadRef.current) {
      setExchanges([]);
      setThreadId(newThreadId());
    }
  }

  const empty = exchanges.length === 0;

  function signOut() {
    closeCurrentChat();
    logout();
    setAuth(null);
    setConversations([]);
    setExchanges([]);
    setThreadId(newThreadId());
  }

  const authControl = auth ? (
    <div className="userchip">
      <span className="userchip__avatar" aria-hidden="true">
        {auth.username.slice(0, 1).toUpperCase()}
      </span>
      <span className="userchip__name">{auth.username}</span>
      <button type="button" className="userchip__out" onClick={signOut}>Log out</button>
    </div>
  ) : (
    <button type="button" className="btn-ghost" onClick={() => setAuthOpen(true)}>
      Log in
    </button>
  );

  return (
    <div className="app">
      <Masthead
        taxYear={taxYear}
        onReset={newChat}
        canReset={!empty && !busy}
        thinking={thinking}
        onToggleThinking={() => setThinking((v) => !v)}
        authControl={authControl}
      />
      <div className={"layout" + (auth ? " layout--rail" : "")}>
        {auth && (
          <ConversationList
            items={conversations}
            activeId={threadId}
            onSelect={openConversation}
            onDelete={removeConversation}
          />
        )}
        <main className="thread" id="thread">
          {empty ? (
            <EmptyState onPick={send} occupation={auth?.occupation} />
          ) : (
            <div className="thread__list">
              {exchanges.map((e) => (
                <Exchange key={e.id} exchange={e} onAsk={send} busy={busy} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </main>
      </div>
      <div className="dock">
        <Composer onSend={send} busy={busy} />
      </div>

      {authOpen && !auth && (
        <Auth
          onAuth={(a) => { setAuth(a); setAuthOpen(false); }}
          onClose={() => setAuthOpen(false)}
        />
      )}
    </div>
  );
}
