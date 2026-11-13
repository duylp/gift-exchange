from nicegui import ui


@ui.page("/")
def index() -> None:
    ui.label("Gift exchange — coming soon 🎁").classes("text-2xl")
