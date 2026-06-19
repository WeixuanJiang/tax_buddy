// Thin client for the knowledge-engine API. Calls go through the Vite proxy
// (/api -> FastAPI) in dev; set VITE_API_BASE for other deployments.
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

const AUTH_KEY = "ke_auth";

export function getAuth() {
  try { return JSON.parse(localStorage.getItem(AUTH_KEY)); } catch { return null; }
}
function setAuth(a) { localStorage.setItem(AUTH_KEY, JSON.stringify(a)); }
export function logout() { localStorage.removeItem(AUTH_KEY); }
function authHeader() {
  const a = getAuth();
  return a?.token ? { Authorization: `Bearer ${a.token}` } : {};
}

export async function register(username, password, occupation, postcode) {
  const a = await post("/auth/register", { username, password, occupation, postcode });
  setAuth(a);
  return a;
}
export async function login(username, password) {
  const a = await post("/auth/login", { username, password });
  setAuth(a);
  return a;
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { headers: { ...authHeader() } });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

export function listConversations() {
  return get("/conversations");
}
export function getConversation(threadId) {
  return get(`/conversations/${encodeURIComponent(threadId)}`);
}
export async function deleteConversation(threadId) {
  const res = await fetch(`${BASE}/conversations/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
    headers: { ...authHeader() },
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}
export async function closeConversation(threadId) {
  const res = await fetch(`${BASE}/conversations/${encodeURIComponent(threadId)}/close`, {
    method: "POST",
    headers: { ...authHeader() },
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail) detail = data.detail;
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  return res.json();
}

// Multi-turn endpoint keeps conversation memory per thread_id.
export function chat(question, threadId) {
  return post("/chat", { question, thread_id: threadId });
}

export function ask(question) {
  return post("/ask", { question });
}

function parseSSE(raw) {
  let event = "message";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  try {
    data = JSON.parse(data);
  } catch {
    /* leave as string */
  }
  return { event, data };
}

// Streamed multi-turn answer over Server-Sent Events.
// Calls onStage(label), onToken(text), onDone(payload), onError(err).
export async function chatStream(question, threadId, handlers, opts = {}) {
  const { onStage, onToken, onDone, onError } = handlers;
  let res;
  try {
    res = await fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({
        question,
        thread_id: threadId,
        reasoning: opts.reasoning ?? false,
      }),
    });
  } catch (e) {
    onError?.(e);
    return;
  }
  if (!res.ok || !res.body) {
    onError?.(new Error(`Request failed (${res.status})`));
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (!raw.trim()) continue;
      const { event, data } = parseSSE(raw);
      if (event === "stage") onStage?.(data.label);
      else if (event === "token") onToken?.(data.text);
      else if (event === "done") onDone?.(data);
      else if (event === "error") onError?.(new Error(data.message || "stream error"));
    }
  }
}
