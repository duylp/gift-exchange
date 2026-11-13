# gift-exchange

Web app for running Secret Santa–style gift exchanges.

## Develop

```sh
cp .env.example .env        # then set SECRET_KEY
uv run python -m gift_exchange.main   # http://localhost:8080, auto-reloads when DEV=1
uv run ruff format . && uv run ruff check . && uv run pytest
```

Project decisions live in `CLAUDE.md`; the task list is `TODO.md`.
