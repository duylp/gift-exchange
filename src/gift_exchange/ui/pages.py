"""The home page `/`: your exchanges (events your email joined), or a welcome + login."""

from fastapi import Request
from nicegui import ui

from gift_exchange.core import db
from gift_exchange.ui.dbconn import open_db
from gift_exchange.ui.layout import account_footer, page_frame
from gift_exchange.ui.login import login_form
from gift_exchange.ui.session import current_admin, current_email


@ui.page("/")
def index(request: Request) -> None:
    """Home page: your exchanges when logged in, otherwise a welcome and the login form.

    Args:
        request: The incoming request (injected by NiceGUI), for the session cookie.
    """
    email = current_email(request)
    ui.page_title("Gift exchange")
    if email is None:
        with page_frame():
            ui.label("Joining an exchange? Open the link from your group chat.")
            ui.label("Already joined? Log in to see your exchanges.").classes("-mt-2")
            login_form("/")
        return

    with open_db() as conn:
        joined = db.list_events_joined_by(conn, email)

    # Styled like the top card (newest event joined); plain if none.
    with page_frame(theme=joined[0].theme if joined else "plain"):
        _your_exchanges(joined)
        if current_admin(request):
            _organiser()
        account_footer(email)


def _your_exchanges(events: list[db.Event]) -> None:
    """Events this person joined, as big clickable cards (the participant view)."""
    ui.label("🎄 Your exchanges").classes("text-lg font-semibold")
    if not events:
        ui.label("You haven't joined any yet. Open the link from your group chat to join.").classes(
            "text-gray-600"
        )
    for event in events:
        status = "You're in · waiting for the draw" if event.is_open else "🎁 See your giftee"
        target = f"/e/{event.slug}"
        card = ui.card().classes("w-full cursor-pointer").props("flat bordered")
        card.on("click", lambda t=target: ui.navigate.to(t))
        with card, ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.column().classes("gap-0"):
                ui.label(event.title).classes("font-semibold")
                ui.label(status).classes("text-sm text-gray-600")
            ui.icon("chevron_right")


def _organiser() -> None:
    """A separate "Organiser" block with a button to the admin pages (admins only)."""
    ui.separator().classes("mt-6")
    ui.label("🛠️ Organiser").classes("text-lg font-semibold")
    ui.label("Create events, see who joined and run the draw.").classes(
        "text-sm text-gray-600 -mt-3"
    )
    ui.button("Manage events", icon="settings", on_click=lambda: ui.navigate.to("/admin")).props(
        "outline"
    ).classes("w-full")
