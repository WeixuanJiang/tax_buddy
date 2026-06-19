import { useEffect, useMemo, useRef, useState } from "react";
import { chatStream, getAuth, logout } from "./api.js";
import Auth from "./components/Auth.jsx";
import Masthead from "./components/Masthead.jsx";
import EmptyState from "./components/EmptyState.jsx";
import Composer from "./components/Composer.jsx";
import Exchange from "./components/Exchange.jsx";

function newThreadId() {
  return `web-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function App() {
  const [exchanges, setExchanges] = useState([]);
  const [busy, setBusy] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [threadId, setThreadId] = useState(newThreadId);
  const [auth, setAuth] = useState(getAuth);
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
  }

  function reset() {
    setExchanges([]);
    setThreadId(newThreadId());
  }

  const empty = exchanges.length === 0;

  return (
    <div className="app">
      <Masthead
        taxYear={taxYear}
        onReset={reset}
        canReset={!empty && !busy}
        thinking={thinking}
        onToggleThinking={() => setThinking((v) => !v)}
      />

      <div className="authbar">
        {auth ? (
          <span>Signed in as <b>{auth.username}</b>{" "}
            <button onClick={() => { logout(); setAuth(null); }}>Log out</button>
          </span>
        ) : (
          <Auth onAuth={setAuth} />
        )}
      </div>

      <main className="thread" id="thread">
        {empty ? (
          <EmptyState onPick={send} />
        ) : (
          <div className="thread__list">
            {exchanges.map((e) => (
              <Exchange key={e.id} exchange={e} onAsk={send} busy={busy} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </main>

      <div className="dock">
        <Composer onSend={send} busy={busy} />
      </div>
    </div>
  );
}
