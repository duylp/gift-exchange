"""Shared page layout: a centred column with a link home at the top."""

from nicegui import ui


def page_frame(max_width: str = "max-w-md") -> ui.column:
    """The column every page builds into, starting with a "🎁 Gift exchange" link to `/`.

    Use as `with page_frame(): ...`.

    Args:
        max_width: Tailwind max-width class for the column (wider for admin pages).
    """
    frame = ui.column().classes(f"w-full {max_width} mx-auto gap-4 p-4")
    with frame:
        ui.link("🎁 Gift exchange", "/").classes(
            "text-sm font-semibold text-gray-600 no-underline hover:underline"
        )
    return frame


def account_footer(email: str) -> None:
    """The "Logged in as … · Log out" line at the bottom of a page."""
    ui.separator().classes("mt-4")
    with ui.row().classes("w-full justify-between text-sm text-gray-500"):
        ui.label(f"Logged in as {email}")
        ui.link("Log out", "/logout")
