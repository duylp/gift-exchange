# gift-exchange

A web app for running Secret Santa gift exchanges with a group of friends.

## Guiding principles
- **Simple first:** ship core features fast with the plainest thing that works; defer anything not needed for the next event.
- **Christmas-first:** the app is built for one Christmas exchange a year (`xmas-2026`, `xmas-2027`, …). Write Christmas wording and defaults directly; don't make things configurable or occasion-neutral for other occasions.

## Match secrecy (most important rule)
Nobody can see who got whom in the app, organiser included. Matches aren't encrypted in the DB: server access or `SECRET_KEY` (forging a login) could reveal them, so it's an honour system.
- `core/db/matches.py:get_giftee` is the only code that reads `matches` (a test enforces it). `run_matching` returns only a count. Never add a query that lists matches.
- The admin may also be a participant, so admin pages never show nicknames (nickname → name would reveal their giftee; `tests/test_admin_secrecy.py`).
- Nothing may hint at matches: no stored seed, no "is my guess right?" check before the reveal.

## Stack and infrastructure
- **Stack:** Python 3.12 (uv), NiceGUI (exact version pinned), SQLite via stdlib `sqlite3`, Resend for email.
- **NiceGUI:** its API changes between major versions, so check https://nicegui.io/documentation for the pinned version before writing UI code. Keep all state in the DB, not in UI elements (phones drop WebSocket connections). Don't use `app.storage.user`.
- **Hosting:** DigitalOcean 1 GB Droplet (SGP1), Docker Compose + Caddy (HTTPS), image built on the Droplet, runs as root in `/opt/gift-exchange`. Steps: `docs/deploy.md`. Deferred: CI/GHCR, arm64 images.
- **Domain:** `santa.mangobello.dev`, events at `/e/<slug>`; email from `mail.mangobello.dev`. Cloudflare is registrar + DNS; the app record is DNS-only so Caddy terminates TLS.
- **Repo:** public on GitHub; secrets are never committed.
- **Config:** `.env` (gitignored) holds only deployment settings and secrets. Outside `DEV=1`, `RESEND_API_KEY`, `EMAIL_FROM` and an `https://` `BASE_URL` are required. Everything about an event lives in the DB, managed on the admin page.
- **Migrations:** own engine `src/sqlite_migrate/`: forward-only numbered SQL files, applied at startup after an automatic DB snapshot. No ORM; the schema exists only in the SQL. See `docs/migrations.md`.
- **Backups:** manual for now (`docs/deploy.md`); R2 later.

## Auth
- Magic link (itsdangerous) → signed `session` cookie holding the email (30 days, HttpOnly, Secure on https, SameSite=Lax); nothing stored server-side.
- Login link valid 15 minutes and reusable within it (mail scanners pre-open links); one email per address per minute.
- Flow: `/login?next=…` → email → `/auth?token=…&next=…` → redirect to `next` (same-site paths only). `/logout` clears the cookie. Errors use fixed codes (`?error=expired|invalid`), never URL text.
- Pages take `request: Request` and call `ui/session.py:current_email(request)` (per-page checks, not middleware). Admin = email in `ADMIN_EMAILS`. Rotating `SECRET_KEY` logs everyone out.
- Email: `httpx` POST to Resend (no SDK) with a `User-Agent` header (403 without one). With `DEV=1`, emails and login links print to the terminal.

## Features
- **People:** no users table; a person is their email. One participant row per email per event (real name, nickname, answers). Cross-event features match on email.
- **Organiser:** a single admin (`ADMIN_EMAILS`) runs every event.
- **Events:** slug, title, budget (whole S$), clue questions, theme (`christmas` default, or `plain`; styles in `ui/themes.py`). Status `open` → `matched` (final).
- **Sign-up** (anyone with the link): real name (organiser and reveal only), nickname (shown to their Santa), answers. Editable until matching. Questions lock once anyone joins.
- **Question sections** (`db.Section`): stored as JSON in `events.questions`; answers are one flat list. A hidden section (reveal prompts) is answered at sign-up but never shown to the Santa.
- **Matching** (`core/matching/`): no self, no reciprocal pairs, two-way exclusions.
  - Shuffle-until-valid with an attempt cap: exactly uniform. Never greedy edge-picking (biased, dead-ends).
  - Feasibility, live on the admin page: anyone with < 2 allowed people → impossible (named); everyone with ≥ n/2 allowed → guaranteed (Dirac); couples-only with n ≥ 4 → guaranteed; otherwise "probably impossible" if the cap is hit.
  - Takes an `rng`: seeded in tests, `random.SystemRandom` in production.
- **Giftee guesses** (`core/db/guesses.py`): after matching, each Santa picks which participant (real names, everyone but themselves) is behind their giftee's nickname. Changeable until the admin presses **Close guesses** (final). Only the guesser sees their guess; the admin sees a count. Any other participant is accepted and correctness is never checked, so guesses can't probe the matches.

## Pages
- Every page builds inside `ui/layout.py:page_frame()`.
- **Home** `/` (`ui/pages.py`): login form, or the events this email joined plus an Organiser section for admins. Never lists events the person hasn't joined.
- **Event** `/e/<slug>` (`ui/event_page.py`): state worked out from the DB on every load: login / sign-up / "you're in" (edit with `?edit=true`) / giftee + guess card / closed. Shows only a participant count publicly, plus "How it works". After any change it navigates to itself.
- **Admin** `/admin`, `/admin/e/<slug>` (`ui/admin_page.py`): events, create form, settings, people, exclusions, feasibility, run matching, guess count + Close guesses, delete (open events only).

## Roadmap
- **Next (stretch):** big-screen party reveal: organiser clicks through pairs, with say-this prompts from the hidden section and guess scoring.
- **Later:** anonymous Santa↔giftee chat, wishlist, copy questions from last year, auto last-year exclusions, R2 backups, CI.

## Data model
Schema in `src/gift_exchange/core/db/migrations/`. Tables: events, participants, exclusions, matches, guesses.
- After matching, DB triggers block joins, sign-up edits, exclusion and budget changes, and deleting participants or the event. Title and theme stay editable.
- Deleting an event is a soft delete (`events.deleted_at`): every query ignores it, nothing is erased, and the slug stays taken. Restore by hand.
- Same-event integrity via composite FKs `(event_id, participant id)`; exclusions are stored once per pair with `a_id < b_id`.
- All tables `STRICT`; timestamps are UTC ISO-8601 text. UI dates are shown in the viewer's time zone (`layout.local_date_label`).

## Code conventions
- **Layout:** `src/gift_exchange/core/` (plain Python) and `ui/` (NiceGUI pages only). Core subpackages (`matching`, `db`, `auth`, `email`) re-export their API from `__init__.py`: `from gift_exchange.core import db` → `db.join_event(...)`.
- **`src/sqlite_migrate/`** is standalone (future own repo): never import `gift_exchange` from it (a test enforces this).
- **DB access:** all SQL lives in `core/db/` and returns dataclasses; the UI never writes SQL. Expected failures raise `DbError` subclasses with user-safe messages.
- **Style:** type hints everywhere; Google-style docstrings (`Args:`/`Returns:`/`Raises:`) on public functions; ruff for lint and format.
- **Tests:** pytest for core only, mirrored under `tests/core/<component>/` (unique file names). UI is checked by hand.
- **Run:** `cp .env.example .env` (set `SECRET_KEY`), then `uv run python -m gift_exchange.main` (auto-reloads with `DEV=1`). Sample data: `uv run python -m gift_exchange.seed`. No console-script entry point (breaks NiceGUI reload).
- **Before commit:** `uv run ruff format . && uv run ruff check . && uv run pytest`
- **Git:** commit straight to `main`, small commits. [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `<type>(<scope>): <description>`. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `style`, `build`, `ci`, `chore`. Scopes: `ui`, `db`, `matching`, `auth`, `email`, `migrate`, `deploy`. Breaking changes: `!` and a `BREAKING CHANGE:` footer.

## Task list
`TODO.md` (local, gitignored) tracks tasks only; facts and decisions live here. Tick items off when done.
