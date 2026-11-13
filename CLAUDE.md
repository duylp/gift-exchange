# gift-exchange

A web app for running Secret Santa–style gift exchanges with a group of friends (Singapore-based).
Successor to a 2021 one-off script in `~/side-projects/xmas` (kept as reference; do not copy its CSVs or `client_secret.json`).

## Guiding principle
Keep things as simple as possible to ship core features fast. Prefer the plainest thing that works; defer anything not needed for the first event.

## Decisions so far
- **Stack:** NiceGUI (pin exact version) + SQLite via stdlib `sqlite3` + magic-link login (itsdangerous) + Resend for email. Python 3.12, managed with uv.
- **NiceGUI caution:** its API changes between major versions — check the pinned version's docs/examples before writing UI code. Keep core logic (matching, DB, auth) in plain Python, separate from the UI layer. Keep all state in the DB, not in UI elements (phones drop WebSocket connections).
- **Hosting:** DigitalOcean 1 GB Droplet in SGP1, Docker Compose + Caddy for HTTPS. For now, build the image on the Droplet (`docker compose up --build`); no CI pipeline yet. Deferred: GitHub Actions → GHCR, and arm64 images (only when a Raspberry Pi is actually used).
- **Domain:** `duylp.dev` (to be registered); app at `santa.duylp.dev`, events at `/e/<slug>` (e.g. `xmas-2026`). Resend sending domain `mail.duylp.dev`.
- **DNS / registrar:** Cloudflare (registrar + DNS). App record is DNS-only (proxy off) so Caddy terminates TLS.
- **Repo:** public on GitHub. Secrets never committed.
- **Config:** `.env` (gitignored) holds only deployment settings and secrets — admin email, secret key, Resend key/sender, base URL, DB path. Everything about an event lives in the DB and is managed via the admin page.
- **Migrations:** own minimal engine `sqlite_migrate` — forward-only numbered plain-SQL scripts, auto-applied at startup; a DB snapshot is taken before every run for rollback. No Alembic, no ORM — the schema exists only in the SQL files. App usage: `docs/migrations.md`; engine design: `src/sqlite_migrate/README.md`.
- **Backups:** SQLite → Cloudflare R2. Not needed in the first stage of development.
- **Auth:** magic link (itsdangerous) → long-lived signed session cookie (~60 days). A plain route `/auth?token=…` verifies the link and sets an itsdangerous-signed cookie holding `user_id`; pages read it from the request. Do not use NiceGUI `app.storage.user` (it stores state in `.nicegui/` files outside the DB).
- **Email:** `httpx` POST to the Resend API (no SDK). Dev backend prints the link to the console.
- **Multi-event:** the app is occasion-agnostic; an event has just a slug, title and budget (no themes/branding in v1).

## v1 scope
- **Organiser:** the repo owner hosts all events. Single admin, identified by email from an env var (`ADMIN_EMAILS`); no per-event organiser roles in v1.
- **Identity:** one account per email (User) across events; a Participant row per user per event. (Deferred: deriving "last year's match" exclusions automatically — no previous event exists yet.)
- **Joining:** anyone with the event link `/e/<slug>` can sign up; organiser can remove people before matching.
- **Budget:** one fixed amount per event, set by the organiser.
- Sign-up: real name (on the user, shown to the organiser and at the reveal; prefilled next time), anonymous nickname (per event, shown to their Santa), answers to the event's clue questions. Editable until the event is matched.
- **Questions are locked** once anyone has signed up (DB trigger); answers are stored in question order.
- **Admin page** (one plain page, admin only): create event (slug, title, budget); clue questions as a textarea, one per line (stored as JSON on the Event); participant list with remove; exclusions via two dropdowns + add; "Run matching" button that works only once per event.
- **Matching** (`core/matching/`): no self, no reciprocal pairs, two-way exclusions (entered on the admin page).
  - Algorithm: shuffle-until-valid (rejection sampling) with an attempt cap — exactly uniform over valid assignments. Not greedy edge-picking (2021 approach: biased, dead-ends).
  - Feasibility, checked up front and live on the admin page: anyone with < 2 allowed people → impossible (name them); everyone allowed with ≥ n/2 others → guaranteed (Dirac). Couples-only with n ≥ 4 is always guaranteed. Otherwise shuffle and report "probably impossible" if the cap is hit.
  - Randomness: function takes an `rng`; tests pass a seeded one, production uses `random.SystemRandom`. No seed is stored or shown (it would reveal matches).
  - Assignment splits into loops (A→B→C→A) for the chain-style reveal.
- **Match secrecy:** hidden from everyone in the app, organiser included (no screen shows them). Not encrypted in the DB. `core/db/matches.py:get_giftee` is the only function that reads `matches` (a test enforces it) and `run_matching` returns only a count — never add a query that lists matches.
- "Your giftee" page: clues, budget
- Stretch (only if v1 ships early): party reveal screen (big screen) with say-this/pose prompts: organiser clicks through pairs; guests submit guess-your-Santa guesses on their phones; scoring.
- Later: anonymous Santa↔giftee chat, voting, wishlist, copy questions from a previous event, auto last-year exclusions, themes, R2 backups, CI/GHCR + arm64 images

## Code conventions
- **Layout:** `src/gift_exchange/` package with `core/` (plain Python) and `ui/` (NiceGUI pages only). Each core component is a subpackage with one module per area, re-exporting its public API from `__init__.py` (callers use `from gift_exchange.core import db` → `db.join_event(...)`): `core/matching/`, `core/db/` (schema SQL in `core/db/migrations/`, shipped with the package); later `core/auth/`, `core/email/`. Tests mirror it under `tests/core/<component>/` (test file names must be unique across the tree).
- **`src/sqlite_migrate/`** is a standalone package meant to become its own repo later: it must never import `gift_exchange` (a test enforces this), and its tests live in `tests/sqlite_migrate/`.
- **DB access:** stdlib `sqlite3`; all queries in the `core/db/` package, returning dataclasses. UI never writes SQL. Expected failures raise `DbError` subclasses (`NicknameTaken`, `EventClosed`, …) whose messages are safe to show users.
- **Types:** type hints everywhere; no type checker in v1.
- **Docstrings:** Google style (`Args:` / `Returns:` / `Raises:`) on public functions and classes, explaining every parameter.
- **Lint/format:** ruff (check + format).
- **Tests:** pytest for core only (matching, migrations, DB queries, auth tokens). UI is checked by hand.
- **Run:** `cp .env.example .env` (set `SECRET_KEY`), then `uv run python -m gift_exchange.main` — auto-reloads when `DEV=1`. Sample data: `uv run python -m gift_exchange.seed` (DEV only; event `xmas-2026`, 8 fake people). Same command in Docker. No console-script entry point (breaks NiceGUI reload). Docker is for deployment only.
- **Check before commit:** `uv run ruff format . && uv run ruff check . && uv run pytest`
- **Git:** commit straight to `main`; small commits, at least one per finished TODO step.

## Data model
Schema: `src/gift_exchange/core/db/migrations/` (start at `0001_initial.sql`). Tables: users, events, participants, exclusions, matches. Later features add their own tables by migration (messages, guesses).
- Event status `open` → `matched` (final). After matching, the DB blocks joins, sign-up edits, exclusion changes and deleting matched participants (triggers + FKs).
- Same-event integrity via composite FKs `(event_id, participant id)`; exclusions stored once per pair with `a_id < b_id`.
- All tables `STRICT`; timestamps UTC ISO-8601 text; budget whole S$.

## Task list
`TODO.md` tracks tasks and progress only; it refers back here for facts. Record facts and decisions here, never duplicated in TODO.md. Tick items off as they are done.
