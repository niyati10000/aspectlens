# SECURITY_AND_ACCESS.md — Keys, Hosting, Abuse Prevention

## 1. Threat model (realistic for this project)
Public demo, no accounts, free hosting. Real risks: **resource exhaustion** (big inputs, spam), **malicious CSV uploads**, **leaked tokens**, **PII in reviews**, **stack-trace leaks**. Not in scope: payments, user data protection beyond PII stripping.

## 2. Keys and secrets
| Secret | Needed? | Where it lives |
|---|---|---|
| Hugging Face token (write) | Only to deploy the Space | Local env / `huggingface-cli login`; **never** in repo |
| GitHub token / SSH key | Only to push | Local credential manager; never in repo |
| Space runtime secrets | Only if you add an optional admin key | HF Space **Settings → Secrets** |
| Third-party paid APIs | **None.** All models run locally | — |

Rules: `.env` in `.gitignore`; commit `.env.example` with names only; scan before every push (`git log -p | grep -iE "hf_|ghp_|token|secret"`); if a token leaks, **revoke it immediately** and rotate.

Optional: `ADMIN_API_KEY` env var gating `POST /upload` and DB-purge routes (header `X-API-Key`). Constant-time compare (`secrets.compare_digest`). If unset, uploads stay open but heavily capped.

## 3. Hosting options
| Option | Cost | Pros | Cons |
|---|---|---|---|
| **Hugging Face Spaces (Docker, CPU basic)** — *chosen* | Free | Simple, HTTPS built in, git-based deploy, ML-friendly | Sleeps when idle, ~16 GB RAM / 2 vCPU, ephemeral disk |
| Hetzner / DigitalOcean VPS | ~€4–6/mo | Always on, full control | You manage OS, SSL, updates |
| Oracle Cloud free tier | Free | Generous ARM VM | Signup friction, capacity limits |
| Render / Fly.io free tiers | Free/limited | Easy deploys | Tighter RAM; may not fit transformer |

**Domain/SSL:** the free `*.hf.space` URL already has HTTPS. A custom domain is optional (~$10/yr); on a VPS use Caddy or Nginx + Let's Encrypt.

**Ephemeral disk note:** HF free Spaces lose files on restart. Treat SQLite as a **cache seeded from the demo sample** on boot; uploaded data is temporary and that is fine for a demo.

## 4. Abuse-prevention checklist
**Input limits**
- [ ] Max review length (e.g. 2,000 chars) → `413/422` with JSON error
- [ ] Max batch size (e.g. 50 reviews)
- [ ] Max CSV size (e.g. 2 MB) and row cap (e.g. 2,000)
- [ ] Reject non-UTF-8 / non-CSV content types; ignore extra columns
- [ ] Pydantic validation on every body/query param

**Rate limiting**
- [ ] Per-IP limits (e.g. `slowapi`): `/analyze` 30/min, `/analyze/batch` 5/min, `/upload` 3/min
- [ ] Respect `X-Forwarded-For` correctly behind the HF proxy
- [ ] Return `429` with a friendly JSON error + `Retry-After`

**Resource protection**
- [ ] Models loaded once; per-request timeout; limit concurrent heavy jobs (semaphore of 2)
- [ ] Batch processed in chunks; no unbounded queues

**CSV / data safety**
- [ ] Treat uploads as untrusted text; never `eval`; parse with `csv`/`pandas` safely
- [ ] Neutralise formula injection if ever exporting CSV (prefix cells starting with `= + - @` with `'`)
- [ ] Parameterised SQL only
- [ ] Sanitise text before rendering: frontend uses `textContent` / escape HTML; never `innerHTML` with review text

**Web hardening**
- [ ] CORS: same-origin by default; allowlist only if a separate frontend origin is needed — never `*` with credentials
- [ ] Security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a basic `Content-Security-Policy` (self + pinned Chart.js)
- [ ] Global exception handler → JSON error; **no stack traces** to clients; log server-side only
- [ ] `/docs` may stay public (read-only demo); disable in any non-demo deployment

**Privacy**
- [ ] Regex-strip emails, phone numbers, URLs with usernames; do not store/display reviewer names
- [ ] No cookies, no analytics trackers, no accounts
- [ ] About page states: reviews are not verified; scores are indicators; uploads are temporary

**Container**
- [ ] Non-root user, slim base image, pinned deps, no secrets baked into the image
- [ ] `.dockerignore` excludes `.git`, `.env`, datasets, notebooks, caches

**Dependency hygiene**
- [ ] Pin versions; run `pip-audit` before release

## 5. Access model
| Actor | Can do |
|---|---|
| Anyone (public) | Analyze text, browse demo products, compare, view evaluation, read docs |
| Admin (holds `ADMIN_API_KEY`, optional) | Upload CSV, purge uploads |
| Developer (you) | Deploy via HF/GitHub tokens held locally |

## 6. Incident basics
Token leaked → revoke, rotate, rewrite history if committed. Space abused → lower rate limits, set `ADMIN_API_KEY`, or pause the Space. Bad data uploaded → purge by `batch_id`.

## 7. Ethics notes (copy into README/About)
Fake or incentivised reviews can distort results; this tool summarises, it does not verify. Aspect scores are indicators, not facts; show counts. Domain shift (laptops → restaurants) reduces accuracy; report honestly.
