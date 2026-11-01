import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";
import { ApiError, api } from "../api";
import type { CodeSent, User } from "../types";
import { AgentObject, BrandMark, Icon, type AgentKey } from "./Art";

export { BrandMark };

type Mode = "login" | "signup";

interface Props {
  onSignedIn: (user: User) => void;
  initialMode?: Mode;
}

/** What the headline cycles through: one line per agent, each with its object. */
const ROTATION: { agent: AgentKey; text: string }[] = [
  { agent: "research", text: "researches your market" },
  { agent: "blog", text: "writes your SEO blog" },
  { agent: "linkedin", text: "drafts your LinkedIn post" },
  { agent: "image", text: "designs your visuals" },
  { agent: "strategist", text: "plans your content" },
];

function usePrefersReducedMotion() {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    setReduce(mq.matches);
    const on = () => setReduce(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduce;
}

function RotatingLine() {
  const reduce = usePrefersReducedMotion();
  const [i, setI] = useState(0);
  useEffect(() => {
    if (reduce) return;
    const t = setInterval(() => setI((n) => (n + 1) % ROTATION.length), 2600);
    return () => clearInterval(t);
  }, [reduce]);
  const item = ROTATION[i];
  return (
    <span className="rotator" aria-hidden="true">
      <span key={item.text} className="rotator__item">
        {item.text}
        <span className="rotator__obj">
          <AgentObject agent={item.agent} size={52} />
        </span>
      </span>
    </span>
  );
}

/** The sign-in landing page: centred hero with the email form, plus a short "learn more" section. */
export function AuthScreen({ onSignedIn, initialMode = "login" }: Props) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [sent, setSent] = useState<CodeSent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; code?: string } | null>(null);
  const more = useRef<HTMLElement>(null);

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
    <div className="landing">
      <header className="landing__bar">
        <span className="landing__brand">
          <BrandMark size={26} />
          ContentBlitz
        </span>
      </header>

      <main className="hero">
        <BrandMark size={64} className="hero__mark" />
        {sent ? (
          <CodeStep
            sent={sent}
            name={name}
            onBack={() => setSent(null)}
            onResend={() => requestCode()}
            onSignedIn={onSignedIn}
          />
        ) : (
          <>
            {mode === "login" ? (
              <h1 className="hero__title">
                <span className="sr-only">ContentBlitz, AI that researches, writes and designs your content</span>
                <span aria-hidden="true">
                  ContentBlitz, AI that
                  <br />
                  <RotatingLine />
                </span>
              </h1>
            ) : (
              <h1 className="hero__title hero__title--small">Create your account</h1>
            )}
            <form className="auth__form" onSubmit={requestCode} noValidate>
              <h2 id="auth-title" className="auth__lede">
                {mode === "login" ? "Log in or create an account" : "Tell us your name. We'll email you a code to confirm."}
              </h2>
              {mode === "signup" && (
                <label className="pill-field">
                  <span className="sr-only">Your name</span>
                  <input
                    autoFocus
                    autoComplete="name"
                    placeholder="Your name"
                    value={name}
                    maxLength={80}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </label>
              )}
              <label className="pill-field">
                <span className="sr-only">Email</span>
                <input
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder="Work email address"
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
                    <button type="button" className="linkish linkish--accent" onClick={() => switchTo("signup")}>
                      Sign up with this email
                    </button>
                  )}
                  {error.code === "already_registered" && (
                    <button type="button" className="linkish linkish--accent" onClick={() => switchTo("login")}>
                      Log in instead
                    </button>
                  )}
                </div>
              )}
              <button
                type="submit"
                className="btn btn--primary btn--pill btn--block"
                disabled={busy || !email.trim() || (mode === "signup" && !name.trim())}
              >
                {busy ? "Sending code…" : mode === "login" ? "Continue" : "Create account"}
              </button>
              <p className="auth__note">
                {mode === "login" ? (
                  <>
                    We'll email you a 6-digit code. New here?{" "}
                    <button type="button" className="linkish linkish--accent" onClick={() => switchTo("signup")}>
                      Sign up
                    </button>
                  </>
                ) : (
                  <>
                    Already have an account?{" "}
                    <button type="button" className="linkish linkish--accent" onClick={() => switchTo("login")}>
                      Log in
                    </button>
                  </>
                )}
              </p>
            </form>
          </>
        )}
        <button
          type="button"
          className="float-pill hero__more"
          onClick={() => more.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
        >
          Learn more <Icon.ArrowDown />
        </button>
      </main>

      <section ref={more} className="tour" aria-labelledby="tour-title">
        <div className="tour__stage" aria-hidden="true">
          <span className="tour__center"><BrandMark size={40} /></span>
          {(["query_handler", "research", "strategist", "blog", "linkedin", "image"] as AgentKey[]).map((a, i) => (
            <span key={a} className={`tour__obj tour__obj--${i + 1}`}>
              <AgentObject agent={a} size={72} />
            </span>
          ))}
        </div>
        <h2 id="tour-title" className="tour__title">Six agents, one conversation</h2>
        <div className="tour__points">
          <div>
            <h3>Research you can check</h3>
            <p>Every finding cites its source, sources get a credibility rating, and figures are checked against them.</p>
          </div>
          <div>
            <h3>Writing that ranks and reads well</h3>
            <p>SEO blog posts and LinkedIn posts are scored for quality and rewritten automatically when they fall short.</p>
          </div>
          <div>
            <h3>Always in your brand voice</h3>
            <p>Set your tone and phrases to avoid, or paste a few samples and ContentBlitz learns how you write.</p>
          </div>
        </div>
        <p className="tour__foot">ContentBlitz · Research, blog posts, LinkedIn posts and visuals from one conversation.</p>
      </section>
    </div>
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
      <h1 id="auth-title" className="hero__title hero__title--small">
        <Icon.Mail size={30} className="hero__title-icon" /> Check your email
      </h1>
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
      <button type="submit" className="btn btn--primary btn--pill btn--block" disabled={busy || code.length !== 6}>
        {busy ? "Checking…" : sent.purpose === "signup" ? "Verify and create account" : "Verify and sign in"}
      </button>
      <p className="auth__note">
        <button type="button" className="linkish linkish--accent" onClick={onResend} disabled={wait > 0}>
          {wait > 0 ? `Send a new code in ${wait}s` : "Send a new code"}
        </button>
        <span aria-hidden="true"> or </span>
        <button type="button" className="linkish linkish--accent" onClick={onBack}>
          use a different email
        </button>
      </p>
    </form>
  );
}

