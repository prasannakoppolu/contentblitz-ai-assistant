import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";
import { ApiError, api } from "../api";
import type { CodeSent, User } from "../types";

type Mode = "login" | "signup";

interface Props {
  onSignedIn: (user: User) => void;
  initialMode?: Mode;
}

/** Centered sign-in / sign-up card. Both paths confirm the email with a 6-digit code. */
export function AuthScreen({ onSignedIn, initialMode = "login" }: Props) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [sent, setSent] = useState<CodeSent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; code?: string } | null>(null);

  const switchTo = (m: Mode) => {
    setMode(m);
    setError(null);
    setSent(null);
  };

  const requestCode = async (e?: FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setSent(mode === "login" ? await api.loginStart(email) : await api.signupStart(email, name));
    } catch (err) {
      const ae = err as ApiError;
      setError({ text: ae.message, code: ae.code });
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <div className="auth__card" role="dialog" aria-modal="false" aria-labelledby="auth-title">
        <p className="auth__brand">
          <BrandMark />
          ContentBlitz
        </p>
        {sent ? (
          <CodeStep
            sent={sent}
            name={name}
            onBack={() => setSent(null)}
            onResend={() => requestCode()}
            onSignedIn={onSignedIn}
          />
        ) : (
          <form className="auth__form" onSubmit={requestCode} noValidate>
            <h1 id="auth-title">{mode === "login" ? "Sign in" : "Create your account"}</h1>
            <p className="auth__lede">
              {mode === "login"
                ? "Enter your work email and we'll send you a sign-in code."
                : "Tell us who you are. We'll email a code to confirm the address."}
            </p>
            {mode === "signup" && (
              <label className="field">
                <span>Your name</span>
                <input
                  autoFocus
                  autoComplete="name"
                  value={name}
                  maxLength={80}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </label>
            )}
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                inputMode="email"
                autoComplete="email"
                autoFocus={mode === "login"}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!error}
                aria-describedby={error ? "auth-error" : undefined}
                required
              />
            </label>
            {error && (
              <div id="auth-error" className="auth__error" role="alert">
                <p>{error.text}</p>
                {error.code === "not_registered" && (
                  <button type="button" className="linkish" onClick={() => switchTo("signup")}>
                    Sign up with this email
                  </button>
                )}
                {error.code === "already_registered" && (
                  <button type="button" className="linkish" onClick={() => switchTo("login")}>
                    Log in instead
                  </button>
                )}
              </div>
            )}
            <button
              type="submit"
              className="btn btn--primary btn--block"
              disabled={busy || !email.trim() || (mode === "signup" && !name.trim())}
            >
              {busy ? "Sending code…" : mode === "login" ? "Send sign-in code" : "Send verification code"}
            </button>
            <p className="auth__switch">
              {mode === "login" ? (
                <>
                  New to ContentBlitz?{" "}
                  <button type="button" className="linkish" onClick={() => switchTo("signup")}>
                    Sign up
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button type="button" className="linkish" onClick={() => switchTo("login")}>
                    Log in
                  </button>
                </>
              )}
            </p>
          </form>
        )}
      </div>
      <p className="auth__foot">Research, blog posts, LinkedIn posts and visuals from one conversation.</p>
    </main>
  );
}

function CodeStep({ sent, name, onBack, onResend, onSignedIn }: {
  sent: CodeSent;
  name: string;
  onBack: () => void;
  onResend: () => void;
  onSignedIn: (u: User) => void;
}) {
  const [digits, setDigits] = useState<string[]>(Array(6).fill(""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wait, setWait] = useState(sent.resend_after);
  const refs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    setDigits(Array(6).fill(""));
    setWait(sent.resend_after);
    refs.current[0]?.focus();
  }, [sent]);
  useEffect(() => {
    if (wait <= 0) return;
    const t = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);

  const code = digits.join("");
  const submit = async (value = code, e?: FormEvent) => {
    e?.preventDefault();
    if (value.length !== 6 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { user } = await api.verify(sent.email, value, sent.purpose);
      onSignedIn(user);
    } catch (err) {
      setError((err as Error).message);
      setDigits(Array(6).fill(""));
      refs.current[0]?.focus();
      setBusy(false);
    }
  };

  const fill = (start: number, text: string) => {
    const clean = text.replace(/\D/g, "");
    if (!clean) return;
    const next = [...digits];
    for (let i = 0; i < clean.length && start + i < 6; i++) next[start + i] = clean[i];
    setDigits(next);
    const joined = next.join("");
    refs.current[Math.min(start + clean.length, 5)]?.focus();
    if (joined.length === 6 && !next.includes("")) void submit(joined);
  };
  const onKey = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !digits[i] && i > 0) {
      const next = [...digits];
      next[i - 1] = "";
      setDigits(next);
      refs.current[i - 1]?.focus();
    } else if (e.key === "ArrowLeft" && i > 0) refs.current[i - 1]?.focus();
    else if (e.key === "ArrowRight" && i < 5) refs.current[i + 1]?.focus();
  };
  const onPaste = (i: number, e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    fill(i, e.clipboardData.getData("text"));
  };

  return (
    <form className="auth__form" onSubmit={(e) => submit(code, e)}>
      <h1 id="auth-title">Check your email</h1>
      <p className="auth__lede">
        {sent.purpose === "signup" && name ? `Thanks, ${name.split(" ")[0]}. ` : ""}
        We sent a 6-digit code to <strong>{sent.email}</strong>. It expires in {Math.round(sent.expires_in / 60)} minutes.
      </p>
      {sent.delivery === "console" && (
        <p className="auth__dev" role="note">
          Email isn't set up on this server yet, so the code is in the server log.
          {sent.dev_code && (
            <>
              {" "}Development code: <code>{sent.dev_code}</code>
            </>
          )}
        </p>
      )}
      <fieldset className="otp" aria-describedby={error ? "otp-error" : undefined}>
        <legend>6-digit code</legend>
        <div className="otp__cells">
          {digits.map((d, i) => (
            <input
              key={i}
              ref={(el) => (refs.current[i] = el)}
              className="otp__cell"
              inputMode="numeric"
              autoComplete={i === 0 ? "one-time-code" : "off"}
              maxLength={i === 0 ? 6 : 2}
              value={d}
              aria-label={`Digit ${i + 1}`}
              aria-invalid={!!error}
              disabled={busy}
              onChange={(e) => {
                const v = e.target.value;
                // Typing over a filled cell gives two characters: keep the new one.
                if (v.length === 2 && digits[i]) fill(i, v.replace(digits[i], ""));
                else if (v.length > 1) fill(i, v);
                else if (/^\d$/.test(v)) fill(i, v);
                else if (v === "") setDigits(digits.map((x, j) => (j === i ? "" : x)));
              }}
              onKeyDown={(e) => onKey(i, e)}
              onPaste={(e) => onPaste(i, e)}
            />
          ))}
        </div>
      </fieldset>
      {error && (
        <p id="otp-error" className="auth__error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="btn btn--primary btn--block" disabled={busy || code.length !== 6}>
        {busy ? "Checking…" : sent.purpose === "signup" ? "Verify and create account" : "Verify and sign in"}
      </button>
      <p className="auth__switch">
        <button type="button" className="linkish" onClick={onResend} disabled={wait > 0}>
          {wait > 0 ? `Send a new code in ${wait}s` : "Send a new code"}
        </button>
        <span aria-hidden="true"> or </span>
        <button type="button" className="linkish" onClick={onBack}>
          use a different email
        </button>
      </p>
    </form>
  );
}

export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="brandmark">
      <rect width="32" height="32" rx="7" fill="var(--ink)" />
      <path d="M18 4 8 18h7l-2 10 11-15h-7z" fill="var(--marker)" />
    </svg>
  );
}
