# gift-exchange

A web app for running Secret Santa–style gift exchanges with a group of friends (Singapore-based).
Successor to a 2021 one-off script in `~/side-projects/xmas` (kept as reference; do not copy its CSVs or `client_secret.json`).

## Guiding principle
Keep things as simple as possible to ship core features fast. Prefer the plainest thing that works; defer anything not needed for the first event.

## Decisions so far
- **Stack:** NiceGUI (pin exact version) + SQLite via stdlib `sqlite3` + magic-link login (itsdangerous) + Resend for email. Python 3.12, managed with uv.
- **NiceGUI caution:** its API changes between major versions — check the official docs (https://nicegui.io/documentation) for the pinned version before writing UI code. Keep core logic (matching, DB, auth) in plain Python, separate from the UI layer. Keep all state in the DB, not in UI elements (phones drop WebSocket connections).
- **Hosting:** DigitalOcean 1 GB Droplet in SGP1, Docker Compose + Caddy for HTTPS. For now, build the image on the Droplet (`docker compose up --build`); no CI pipeline yet. Deferred: GitHub Actions → GHCR, and arm64 images (only when a Raspberry Pi is actually used). Runs as root in `/opt/gift-exchange` (no deploy user; see `docs/deploy.md`). Deploy, update, backup and off-season steps: `docs/deploy.md`.
- **Domain:** `mangobello.dev` (registered on Cloudflare); app at `santa.mangobello.dev`, events at `/e/<slug>` (e.g. `xmas-2026`). Resend sending domain `mail.mangobello.dev`.
- **DNS / registrar:** Cloudflare (registrar + DNS). App record is DNS-only (proxy off) so Caddy terminates TLS.
- **Repo:** public on GitHub. Secrets never committed.
- **Config:** `.env` (gitignored) holds only deployment settings and secrets — admin email, secret key, Resend key/sender, base URL, DB path. Outside `DEV=1`, `RESEND_API_KEY`, `EMAIL_FROM` and an `https://` `BASE_URL` are required (startup fails otherwise). Everything about an event lives in the DB and is managed via the admin page.
- **Migrations:** own minimal engine `sqlite_migrate` — forward-only numbered plain-SQL scripts, auto-applied at startup; a DB snapshot is taken before every run for rollback. No Alembic, no ORM — the schema exists only in the SQL files. App usage: `docs/migrations.md`; engine design: `src/sqlite_migrate/README.md`.
- **Backups:** SQLite → Cloudflare R2. Not needed in the first stage of development.
- **Auth:** magic link (itsdangerous, not JWT — same app signs and checks) → own signed session cookie, nothing stored server-side. Chosen over NiceGUI's documented `app.storage.user` (server-side files in `.nicegui/`: needs a volume, piles up, outside the DB).
  - Login link: email signed with `SECRET_KEY`, valid 15 minutes, reusable within that window (mail scanners pre-open links). One email per address per minute (in-memory cooldown).
  - `/login?next=…` (email form) → email → `/auth?token=…&next=…` sets cookie `session` (signed email, 30 days, HttpOnly, Secure on https, SameSite=Lax) → redirect to `next` (same-site paths only). `/logout` clears it. Errors shown via fixed codes (`?error=expired|invalid`), never free text from the URL.
  - Pages take `request: Request` and call `ui/session.py:current_email(request)` while building; per-page checks (not middleware) because event pages are partly public. Admin = email in `ADMIN_EMAILS`. Rotating `SECRET_KEY` logs everyone out.
  - Do not use NiceGUI `app.storage.user`.
- **Email:** `httpx` POST to the Resend API (no SDK); must send a `User-Agent` header (Resend returns 403 without one). Dev backend (`DEV=1`) prints emails, including login links, to the terminal.
- **Multi-event:** the app is occasion-agnostic; an event has a slug, title, budget and theme.
- **Themes:** per event, chosen from presets in code (`db.THEMES` names: `christmas` — the default, `db.DEFAULT_THEME` — and `plain`; styles in `ui/themes.py`). Stored as `events.theme` (no CHECK — a new theme is a code change, no migration; core validates on write, UI falls back to the default). Editable after matching. `/e/<slug>` uses the event's theme; the logged-in home page uses the theme of the newest event the person joined (the top card); logged-out home, login and admin pages use the default theme. No custom colours/CSS from the admin.

## v1 scope
- **Organiser:** the repo owner hosts all events. Single admin, identified by email from an env var (`ADMIN_EMAILS`); no per-event organiser roles in v1.
- **Identity:** no accounts / users table. A person is their email: logging in proves it, and each event has one participant row per email (with real name, nickname, answers). Cross-event features (avoid last year's match, carry couples over, invite past participants) match on email; add a users table by migration only if a per-person feature ever needs it.
- **Joining:** anyone with the event link `/e/<slug>` can sign up; organiser can remove people before matching.
- **Budget:** one fixed amount per event, set by the organiser.
- Sign-up: real name (shown to the organiser and at the reveal), anonymous nickname (per event, shown to their Santa), answers to the event's clue questions. Editable until the event is matched.
- **Questions are locked** once anyone has signed up (DB trigger); answers are stored in question order.
- **Question sections:** questions are grouped in sections (`db.Section`: title, questions, `hidden`), stored as JSON in `events.questions`; answers stay one flat list across all sections. A hidden section (e.g. reveal prompts: what your Santa should say/do) is answered at sign-up but never shown to the Santa — `get_giftee` leaves it out; it's for the party reveal (stretch).
- **Admin pages** (`ui/admin_page.py`, admin only; others redirected to `/login` or `/`): `/admin` lists events + create form (slug, title, budget, clue questions). `/admin/e/<slug>`: share link + copy, settings (questions read-only once anyone joined, budget read-only after matching). Clue questions use a list editor grouped in sections: one box each, reorder ↑↓, remove, add (Enter adds below); each section has an optional title and a "hide from Santa" switch, people (name, email, nickname, remove with confirm), exclusions (two dropdowns + add, delete), live feasibility banner, "Run matching" with a confirm dialog showing counts, delete event (open events only; a soft delete, see **Data model**). Never shows who got whom.
- **Matching** (`core/matching/`): no self, no reciprocal pairs, two-way exclusions (entered on the admin page).
  - Algorithm: shuffle-until-valid (rejection sampling) with an attempt cap — exactly uniform over valid assignments. Not greedy edge-picking (2021 approach: biased, dead-ends).
  - Feasibility, checked up front and live on the admin page: anyone with < 2 allowed people → impossible (name them); everyone allowed with ≥ n/2 others → guaranteed (Dirac). Couples-only with n ≥ 4 is always guaranteed. Otherwise shuffle and report "probably impossible" if the cap is hit.
  - Randomness: function takes an `rng`; tests pass a seeded one, production uses `random.SystemRandom`. No seed is stored or shown (it would reveal matches).
  - Assignment splits into loops (A→B→C→A) for the chain-style reveal.
- **Match secrecy:** hidden from everyone in the app, organiser included (no screen shows them). Not encrypted in the DB. `core/db/matches.py:get_giftee` is the only function that reads `matches` (a test enforces it) and `run_matching` returns only a count — never add a query that lists matches.
- **Layout:** every page builds inside `ui/layout.py:page_frame()`, which starts with a "🎁 Gift exchange" link back to `/`.
- **Home page** `/` (`ui/pages.py`): logged out → welcome + login form; logged in → "🎄 Your exchanges" (events this email joined, via `db.list_events_joined_by`, as clickable cards), then for admins a separate "🛠️ Organiser" section (divider, heading, **Manage events** button to `/admin`). Never lists events the person hasn't joined.
- **Event page** `/e/<slug>` (`ui/event_page.py`): one page, state worked out from the DB on every load — not logged in (login form) / sign-up form / "you're in" with edit (`?edit=true`) / your giftee (nickname, clues, budget) / closed. Shows only a participant count publicly, plus a "How it works" block of the rules built from the event (budget, hidden sections), always shown. After any change it navigates to itself (no UI-only state).
- Stretch (only if v1 ships early): party reveal screen (big screen) with say-this/pose prompts: organiser clicks through pairs; guests submit guess-your-Santa guesses on their phones; scoring.
- Later: anonymous Santa↔giftee chat, voting, wishlist, copy questions from a previous event, auto last-year exclusions, more theme presets, R2 backups, CI/GHCR + arm64 images

## Code conventions
- **Layout:** `src/gift_exchange/` package with `core/` (plain Python) and `ui/` (NiceGUI pages only). Each core component is a subpackage with one module per area, re-exporting its public API from `__init__.py` (callers use `from gift_exchange.core import db` → `db.join_event(...)`): `core/matching/`, `core/db/` (schema SQL in `core/db/migrations/`, shipped with the package), `core/auth/`, `core/email/`. Tests mirror it under `tests/core/<component>/` (test file names must be unique across the tree).
- **`src/sqlite_migrate/`** is a standalone package meant to become its own repo later: it must never import `gift_exchange` (a test enforces this), and its tests live in `tests/sqlite_migrate/`.
- **DB access:** stdlib `sqlite3`; all queries in the `core/db/` package, returning dataclasses. UI never writes SQL. Expected failures raise `DbError` subclasses (`NicknameTaken`, `EventClosed`, …) whose messages are safe to show users.
- **Types:** type hints everywhere; no type checker in v1.
- **Docstrings:** Google style (`Args:` / `Returns:` / `Raises:`) on public functions and classes, explaining every parameter.
- **Lint/format:** ruff (check + format).
- **Tests:** pytest for core only (matching, migrations, DB queries, auth tokens). UI is checked by hand.
- **Run:** `cp .env.example .env` (set `SECRET_KEY`), then `uv run python -m gift_exchange.main` — auto-reloads when `DEV=1`. Sample data: `uv run python -m gift_exchange.seed` (DEV only; event `xmas-2026`, 8 fake people, a hidden reveal section). Same command in Docker. No console-script entry point (breaks NiceGUI reload). Docker is for deployment only.
- **Check before commit:** `uv run ruff format . && uv run ruff check . && uv run pytest`
- **Git:** commit straight to `main`; small commits, at least one per finished TODO step.
  Messages follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/): `<type>(<optional scope>): <description>`, e.g. `fix(ui): keep the sign-up form when a phone switches apps`. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `style`, `build`, `ci`, `chore`. Scopes (optional): `ui`, `db`, `matching`, `auth`, `email`, `migrate`, `deploy`. Breaking changes: `!` after the type/scope and a `BREAKING CHANGE:` footer. Commits before 2026-11-16 don't follow it.

## Data model
Schema: `src/gift_exchange/core/db/migrations/` (start at `0001_initial.sql`). Tables: events, participants, exclusions, matches (no users table — see **Identity**). Later features add their own tables by migration (messages, guesses).
- Event status `open` → `matched` (final). After matching, the DB blocks joins, sign-up edits, exclusion changes, budget changes, and deleting matched participants or the event (triggers + FKs). The title stays editable.
- **Deleting an event is a soft delete:** `events.deleted_at` is set and every query ignores the event (its page 404s, it leaves everyone's home page), but no row is erased. Restore by setting `deleted_at` back to NULL (by hand; no UI). The slug stays taken. Matched events can't be deleted, and deleted ones can't be matched (triggers).
- Same-event integrity via composite FKs `(event_id, participant id)`; exclusions stored once per pair with `a_id < b_id`.
- All tables `STRICT`; timestamps UTC ISO-8601 text; budget whole S$.

## Task list
`TODO.md` (local only, gitignored) tracks tasks and progress only; it refers back here for facts. Record facts and decisions here, never duplicated in TODO.md. Tick items off as they are done.
