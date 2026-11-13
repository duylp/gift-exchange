"""App entry point: `uv run python -m gift_exchange.main`.

Run as a module, not via a console script: NiceGUI auto-reload re-imports the main
module as `__mp_main__`, which only works with `python -m` or a file path.
"""

from nicegui import ui

from gift_exchange import ui as _pages  # noqa: F401  (registers pages)
from gift_exchange.config import load_settings


def main() -> None:
    settings = load_settings()
    ui.run(
        title="Gift Exchange",
        favicon="🎁",
        host=settings.host,
        port=settings.port,
        reload=settings.dev,
        show=False,
        uvicorn_reload_dirs="src",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
