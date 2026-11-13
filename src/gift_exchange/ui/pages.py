from fastapi import Request
from nicegui import ui

from gift_exchange.ui.login import login_url
from gift_exchange.ui.session import current_admin, current_email


@ui.page("/")
def index(request: Request) -> None:
    email = current_email(request)
    with ui.column().classes("w-full max-w-sm mx-auto mt-16 gap-4 p-4"):
        ui.label("Gift exchange 🎁").classes("text-2xl font-bold")
        if email:
            ui.label(f"Logged in as {email}" + (" (organiser)" if current_admin(request) else ""))
            ui.link("Log out", "/logout")
        else:
            ui.label("Open your event's link to join, or log in.")
            ui.link("Log in", login_url("/"))
