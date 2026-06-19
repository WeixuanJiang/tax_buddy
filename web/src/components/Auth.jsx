import { useEffect, useState } from "react";
import { login, register } from "../api.js";

// Centered sign-in / sign-up dialog. Optional: the app stays usable for guests;
// this only opens when someone chooses to log in.
export default function Auth({ onAuth, onClose }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", password: "", occupation: "", postcode: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const isReg = mode === "register";
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function switchMode(next) {
    setErr("");
    setMode(next);
  }

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const a = isReg
        ? await register(form.username, form.password, form.occupation, form.postcode)
        : await login(form.username, form.password);
      onAuth?.(a);
    } catch (e2) {
      setErr(e2.message || "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="authmodal" role="dialog" aria-modal="true"
         aria-label={isReg ? "Create your account" : "Log in"}>
      <div className="authmodal__backdrop" onClick={onClose} />
      <div className="authmodal__card">
        <button className="authmodal__close" type="button" onClick={onClose} aria-label="Close">×</button>

        <span className="authmodal__mark" aria-hidden="true">§</span>
        <h2 className="authmodal__title">{isReg ? "Create your account" : "Welcome back"}</h2>
        <p className="authmodal__sub">
          {isReg
            ? "Save your conversations and get answers tuned to your situation."
            : "Log in to pick up your saved conversations."}
        </p>

        <div className="seg" role="tablist" aria-label="Choose log in or sign up">
          <button type="button" role="tab" aria-selected={!isReg}
                  className={"seg__btn" + (!isReg ? " is-active" : "")}
                  onClick={() => switchMode("login")}>Log in</button>
          <button type="button" role="tab" aria-selected={isReg}
                  className={"seg__btn" + (isReg ? " is-active" : "")}
                  onClick={() => switchMode("register")}>Sign up</button>
        </div>

        <form className="authform" onSubmit={submit}>
          <label className="field">
            <span className="field__label">Username</span>
            <input className="field__input" value={form.username} onChange={set("username")}
                   autoComplete="username" autoFocus placeholder="jane_smith" />
          </label>
          <label className="field">
            <span className="field__label">Password</span>
            <input className="field__input" type="password" value={form.password} onChange={set("password")}
                   autoComplete={isReg ? "new-password" : "current-password"}
                   placeholder={isReg ? "At least 8 characters" : "Your password"} />
          </label>
          {isReg && (
            <div className="field-row">
              <label className="field">
                <span className="field__label">Occupation</span>
                <input className="field__input" value={form.occupation} onChange={set("occupation")}
                       placeholder="e.g. electrician" />
              </label>
              <label className="field field--narrow">
                <span className="field__label">Postcode</span>
                <input className="field__input" value={form.postcode} onChange={set("postcode")}
                       inputMode="numeric" maxLength={4} placeholder="3000" />
              </label>
            </div>
          )}

          {err && <p className="authform__err" role="alert">{err}</p>}

          <button className="authform__submit" type="submit" disabled={busy}>
            {busy ? <span className="composer__spinner" aria-hidden="true" />
                  : isReg ? "Create account" : "Log in"}
          </button>
        </form>

        <p className="authform__switch">
          {isReg ? "Already have an account? " : "New here? "}
          <button type="button" className="linklike" onClick={() => switchMode(isReg ? "login" : "register")}>
            {isReg ? "Log in" : "Create one"}
          </button>
        </p>
      </div>
    </div>
  );
}
