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
    with page_frame():
        if email is None:
            ui.label("Joining an exchange? Open the link from your group chat.")
            ui.label("Already joined? Log in to see your exchanges.").classes("-mt-2")
            login_form("/")
            return

        is_admin = current_admin(request)
        with open_db() as conn:
            joined = db.list_events_joined_by(conn, email)
            managed = db.list_events(conn) if is_admin else []
            counts = {e.id: db.count_participants(conn, e.id) for e in managed}

        _your_exchanges(joined)
        if is_admin:
            _organiser(managed, counts)
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


def _organiser(events: list[db.Event], counts: dict[int, int]) -> None:
    """Organiser panel: every event with its status and a manage link (admins only).

    Kept visually apart from "Your exchanges" (tinted box, compact rows) so taking part
    and running events don't blur together.
    """
    with ui.card().classes("w-full mt-4 bg-slate-50 gap-2").props("flat bordered"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("🛠️ Organiser").classes("text-lg font-semibold")
                ui.label("Only organisers see this.").classes("text-xs text-gray-500")
            ui.button("New event", icon="add", on_click=lambda: ui.navigate.to("/admin")).props(
                "outline dense"
            )
        if not events:
            ui.label("No events yet.").classes("text-sm text-gray-600")
        for event in events:
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                with ui.column().classes("gap-0 min-w-0"):
                    ui.label(event.title).classes("font-medium")
                    ui.label(f"{counts[event.id]} joined · S${event.budget}").classes(
                        "text-xs text-gray-500"
                    )
                with ui.row().classes("items-center gap-2 no-wrap"):
                    if event.is_open:
                        ui.badge("open", color="blue")
                    else:
                        ui.badge("matched", color="green")
                    ui.button(
                        "Manage", on_click=lambda s=event.slug: ui.navigate.to(f"/admin/e/{s}")
                    ).props("flat dense")
