"""The home page `/`: your exchanges (events your email joined), or a welcome + login."""

from fastapi import Request
from nicegui import ui

from gift_exchange.core import db
from gift_exchange.ui.dbconn import open_db
from gift_exchange.ui.layout import page_frame
from gift_exchange.ui.login import login_form
from gift_exchange.ui.session import current_admin, current_email


@ui.page("/")
def index(request: Request) -> None:
    email = current_email(request)
    ui.page_title("Gift exchange")
    with page_frame():
        if email is None:
            ui.label("Joining an exchange? Open the link from your group chat.")
            ui.label("Already joined? Log in to see your exchanges.").classes("-mt-2")
            login_form("/")
            return

        with open_db() as conn:
            events = db.list_events_joined_by(conn, email)

        ui.label("Your exchanges").classes("text-lg font-semibold")
        if not events:
            ui.label(
                "You haven't joined any yet. Open the link from your group chat to join."
            ).classes("text-gray-600")
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

        if current_admin(request):
            ui.button("Manage events", on_click=lambda: ui.navigate.to("/admin")).props(
                "outline"
            ).classes("w-full")

        ui.separator().classes("mt-4")
        with ui.row().classes("w-full justify-between text-sm text-gray-500"):
            ui.label(f"Logged in as {email}")
            ui.link("Log out", "/logout")
