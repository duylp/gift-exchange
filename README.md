# 🎁 gift-exchange

A small web app for running a Secret Santa gift exchange with friends. Everyone signs up from one link, the app draws who gives to whom, and each Santa sees only their giftee's secret nickname and a few clues until the party.

Built to be simple: one Python process, one SQLite file, and passwordless email login.

## How it works

1. **The organiser creates an event** (e.g. `xmas-2026`) with a title, a budget and a few clue questions, then shares the link `/e/xmas-2026`.
2. **Friends sign up** by logging in with their email (a magic link, no password) and filling in:
   - their real name (seen only by the organiser, and at the reveal);
   - a secret nickname (what their Santa sees);
   - answers to the clue questions ("What do you do for fun?", "Anything you're allergic to?").
3. **The organiser runs the draw.** Everyone becomes Santa for one other person, picked at random, with no self-matches, no reciprocal pairs, and optional exclusions (e.g. couples).
4. **Each Santa opens the event page** and sees their giftee's nickname, clues and the budget, never the real name.
5. **Guess who it is.** Before the party, each Santa guesses which participant is behind the nickname. Guesses lock when the organiser closes them.
6. **At the party,** gifts are handed over and identities revealed.

## Privacy by design

Who got whom is secret from everyone in the app, **the organiser included**:

- No screen ever lists the matches. In the code, one function reads them, and it answers only "who does *this* person give to?". A test enforces this.
- Admin pages never show nicknames, so an organiser who also takes part can't work out their giftee.
- Guesses are never checked against the matches before the reveal, so they can't be used to probe them.
- The random draw uses the operating system's randomness, and no seed is stored.

## Features

- **Sign-up from one link,** editable until the draw. Phone-friendly.
- **Clue questions in sections,** including hidden ones answered at sign-up but kept back for the party reveal (e.g. "What should your Santa say when handing you the gift?").
- **Fair matching:** uniformly random over every valid assignment (shuffle until valid). The admin page shows live whether the exclusions still allow a draw, and who is blocking it.
- **Giftee guesses** with a count for the organiser and a **Close guesses** button.
- **Several events,** one per year; each person sees only the events they joined.
- **Festive theme** with falling snow (or a plain one).

## Tech stack

| Part | Choice |
|---|---|
| UI | [NiceGUI](https://nicegui.io) (Python, Vue/Quasar under the hood) |
| Database | SQLite via the standard `sqlite3` module, no ORM |
| Migrations | `sqlite_migrate`, a small built-in engine: numbered SQL files applied at startup, with a snapshot first |
| Login | Magic links and a signed session cookie ([itsdangerous](https://itsdangerous.palletsprojects.com)) |
| Email | [Resend](https://resend.com) HTTP API |
| Hosting | Docker Compose + [Caddy](https://caddyserver.com) (automatic HTTPS) on a small VPS |
| Tooling | Python 3.12, [uv](https://docs.astral.sh/uv/), ruff, pytest |

## Getting started

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
cp .env.example .env                    # then set SECRET_KEY to a long random string
uv run python -m gift_exchange.seed     # optional: sample event xmas-2026 with 8 fake people
uv run python -m gift_exchange.main     # http://localhost:8080
```

With `DEV=1` (the default in `.env.example`) the app reloads on code changes and **prints login emails to the terminal** instead of sending them. Log in as `alex.tan@example.com` to be both organiser and participant in the sample event, then open `/admin`.

Before committing:

```sh
uv run ruff format . && uv run ruff check . && uv run pytest
```

## Project layout

```
src/gift_exchange/
  core/            plain Python, no UI
    matching/      the draw and feasibility checks
    db/            every SQL query; schema in db/migrations/*.sql
    auth/          login tokens and sessions
    email/         Resend client (prints to the terminal in dev)
  ui/              NiceGUI pages: home, event, admin, login
  main.py          entry point: migrate, then serve
  seed.py          sample data for development
src/sqlite_migrate/  standalone migration engine
tests/             pytest, mirroring core/
docs/              deploy and migration guides
```

## Documentation

- [`docs/deploy.md`](docs/deploy.md): server setup, deploying, updating, backups and restore.
- [`docs/migrations.md`](docs/migrations.md): changing the database schema.
- [`src/sqlite_migrate/README.md`](src/sqlite_migrate/README.md): how the migration engine works.
- [`CLAUDE.md`](CLAUDE.md): design decisions and code conventions.
