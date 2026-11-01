# ADR-0006: Email one-time-code accounts, owned conversations and an admin-only dashboard

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Prasanna Koppolu (project owner)

## Context
ContentBlitz is moving from a single-user demo to a product used by customers. The owner asked for:

- a sign-in page centred on the screen; an email that isn't registered must get an error saying so, with a link to
  sign up; sign-up collects the email and sends a one-time code to it;
- the signed-in user's name and a **New conversation** button on the left;
- provider keys, offline mode, the quality/provider comparison and "usage since the server started" removed from the
  customer UI and moved to a dashboard customers can't see.

Until now each browser sent its own provider settings and API keys with every request, every conversation was
reachable by anyone who knew its id, and usage was visible to everyone.

## Decision
1. **Passwordless email + 6-digit one-time code** for both sign-up and log-in. Log-in with an unknown email returns
   `404 not_registered`; sign-up with a known email returns `409 already_registered`. A sign-up account is created
   only when its code is verified, so nobody can register an inbox they don't control.
2. **Server-side sessions** in an HttpOnly, `SameSite=Lax` cookie (14 days, `Secure` behind HTTPS). Tokens and codes are
   stored only as SHA-256 hashes (codes salted) in a SQLite file (`CONTENTBLITZ_AUTH_DB`).
3. **Abuse limits**: codes expire after 10 minutes, 5 wrong tries burn a code, one code per 30 s and 5 per hour per
   email; codes are compared in constant time.
4. **Email delivery** through SMTP when `SMTP_HOST` is set; otherwise codes go to the server log (and, with
   `CONTENTBLITZ_AUTH_DEV_CODES=1`, are returned to the UI) so the whole flow works offline for development and tests.
5. **Conversations are owned**: a `threads` table maps `thread_id` → user, gives the sidebar its list (titled by the
   first message) and makes every thread route return 404 to anyone else.
6. **Server settings move to the server.** Provider keys come only from `.env`. Offline mode, provider priority and
   the quality threshold are saved by admins (`ADMIN_EMAILS`) on `/admin`, which also shows configured keys, provider
   chains, usage/cost and accounts. Customers' requests carry only their message.

## Options Considered

### Option A: Email + one-time code, own sessions in SQLite (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low: ~350 lines, standard library only (`smtplib`, `sqlite3`, `secrets`, `hashlib`) |
| Cost | Free locally; SMTP via any provider (Gmail app password, SendGrid, Mailgun, SES) |
| Scalability | Single instance with SQLite; move the same tables to Postgres for replicas |
| Security | No passwords to leak or reset; inbox control proves identity; hashed secrets at rest |

**Pros:** exactly the flow requested (email, code, sign-up link); no password reset flow; works offline.
**Cons:** depends on email deliverability; sign-in takes one extra step each time (mitigated by 14-day sessions).

### Option B: Email + password
**Pros:** familiar; no email on every log-in. **Cons:** still needs email verification and password reset; storing
password hashes raises the stakes of a database leak; not what was asked.

### Option C: Hosted identity (Auth0, Clerk, Cognito, Google sign-in)
**Pros:** MFA, social log-in, managed security. **Cons:** an external account and keys just to try the app, no
offline mode, vendor lock-in. Worth revisiting if enterprise SSO is needed.

### Option D: JWT in localStorage
**Pros:** stateless. **Cons:** readable by any injected script, can't be revoked on sign-out; HttpOnly cookies avoid
both.

## Trade-off Analysis
The login error intentionally reveals whether an email is registered (the requested behaviour). The per-email send
limits stop this from being used to spam inboxes, but they don't fully prevent enumeration; if that ever matters,
switch to "if this email is registered we sent a code" wording and keep everything else.

## Consequences
- Every API route except health, config and `/api/auth/*` needs a session; `/api/admin/*` needs an admin email.
- The `EngineRegistry` now builds engines from the admin's saved settings rather than per-browser settings; keys never
  travel through the browser.
- Tests sign in through the real flow (`tests/integration/auth_helpers.py`), including Playwright e2e tests.
- Production must set `SMTP_*`, `ADMIN_EMAILS` and `CONTENTBLITZ_COOKIE_SECURE=1`, and keep the auth database on a
  persistent volume.

## Action Items
1. [x] Auth store, service, mailer, routes and ownership checks (`src/auth/`, `src/api/server.py`)
2. [x] Sign-in / sign-up card, sidebar with user and conversations, `/admin` dashboard
3. [ ] Postgres-backed store and a shared rate-limit store before running several replicas
4. [ ] Optional: per-user usage and cost on the admin dashboard
