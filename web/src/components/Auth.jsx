import { useState } from "react";
import { login, register } from "../api.js";

export default function Auth({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", password: "", occupation: "", postcode: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const a = mode === "login"
        ? await login(form.username, form.password)
        : await register(form.username, form.password, form.occupation, form.postcode);
      onAuth?.(a);
    } catch (e2) {
      setErr(e2.message || "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auth" onSubmit={submit}>
      <div className="auth__tabs">
        <button type="button" disabled={mode === "login"} onClick={() => setMode("login")}>Log in</button>
        <button type="button" disabled={mode === "register"} onClick={() => setMode("register")}>Register</button>
      </div>
      <input placeholder="username" value={form.username} onChange={set("username")} autoComplete="username" />
      <input placeholder="password" type="password" value={form.password} onChange={set("password")} autoComplete="current-password" />
      {mode === "register" && (
        <>
          <input placeholder="occupation" value={form.occupation} onChange={set("occupation")} />
          <input placeholder="postcode (4 digits)" value={form.postcode} onChange={set("postcode")} />
        </>
      )}
      {err && <p className="auth__err">{err}</p>}
      <button type="submit" disabled={busy}>{busy ? "…" : mode === "login" ? "Log in" : "Create account"}</button>
    </form>
  );
}
