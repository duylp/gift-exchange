"""Organiser pages: /admin (events + create) and /admin/e/<slug> (manage one event).

Only emails in ADMIN_EMAILS get in. Like the event page, everything is read fresh from the
database on each load and every change navigates back to the page.

Match secrecy: these pages never show who got whom — only counts.
"""

import random

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import ui

from gift_exchange.config import get_settings
from gift_exchange.core import db
from gift_exchange.core.matching import MatchingError, Verdict
from gift_exchange.ui.dbconn import open_db
from gift_exchange.ui.layout import page_frame
from gift_exchange.ui.login import login_url
from gift_exchange.ui.session import current_admin, current_email


def _guard(request: Request) -> RedirectResponse | None:
    """Redirect away unless the visitor is a logged-in organiser."""
    if current_email(request) is None:
        return RedirectResponse(login_url(request.url.path), 303)
    if not current_admin(request):
        return RedirectResponse("/", 303)
    return None


# --- /admin ----------------------------------------------------------------------------------


@ui.page("/admin")
def admin_home(request: Request) -> RedirectResponse | None:
    """The /admin page: all events and a form to create one. Organisers only.

    Args:
        request: The incoming request (injected by NiceGUI), for the session cookie.

    Returns:
        A redirect if the visitor isn't a logged-in organiser, otherwise None.
    """
    if redirect := _guard(request):
        return redirect
    with open_db() as conn:
        events = db.list_events(conn)
        counts = {e.id: db.count_participants(conn, e.id) for e in events}

    ui.page_title("Admin")
    with page_frame("max-w-xl"):
        ui.label("Your events").classes("text-2xl font-bold")
        if not events:
            ui.label("No events yet. Create one below.").classes("text-gray-600")
        for event in events:
            with ui.card().classes("w-full").props("flat bordered"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(event.title).classes("font-semibold")
                    _status_badge(event)
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(f"{counts[event.id]} joined · S${event.budget}").classes(
                        "text-sm text-gray-600"
                    )
                    ui.link("Manage", f"/admin/e/{event.slug}")

        ui.separator()
        _new_event_form()
    return None


def _new_event_form() -> None:
    ui.label("New event").classes("text-lg font-semibold")
    base = get_settings().base_url
    slug = (
        ui.input(
            "Link",
            placeholder="xmas-2026",
            validation={"Required": lambda v: bool(v and v.strip())},
        )
        .props(f'outlined prefix="{base}/e/"')
        .classes("w-full")
    )
    ui.label("Lowercase letters, digits and hyphens.").classes("text-xs text-gray-500 -mt-2")
    title = (
        ui.input("Title", validation={"Required": lambda v: bool(v and v.strip())})
        .props("outlined")
        .classes("w-full")
    )
    budget = ui.number("Budget (S$)", value=30, min=1, precision=0).props("outlined")
    questions = (
        ui.textarea(
            "Clue questions (one per line)",
            placeholder="What do you do for fun?\nFavourite colour?",
        )
        .props("outlined autogrow")
        .classes("w-full")
    )

    def create() -> None:
        results = [slug.validate(), title.validate()]
        if not all(results):
            return
        amount = _whole_number(budget.value)
        if amount is None:
            ui.notify("Budget must be a whole number above 0.", type="warning")
            return
        try:
            with open_db() as conn:
                event = db.create_event(
                    conn,
                    slug.value.strip().lower(),
                    title.value,
                    amount,
                    _lines(questions.value),
                )
        except (db.DbError, ValueError) as exc:
            ui.notify(str(exc), type="negative")
            return
        ui.navigate.to(f"/admin/e/{event.slug}")

    ui.button("Create event", on_click=create).classes("w-full")


# --- /admin/e/<slug> ---------------------------------------------------------------------------


@ui.page("/admin/e/{slug}")
def admin_event(slug: str, request: Request) -> RedirectResponse | None:
    """The /admin/e/<slug> page: manage one event. Organisers only.

    Args:
        slug: The event's URL slug (case is ignored).
        request: The incoming request (injected by NiceGUI), for the session cookie.

    Returns:
        A redirect if the visitor isn't a logged-in organiser, otherwise None.
    """
    if redirect := _guard(request):
        return redirect
    with open_db() as conn:
        try:
            event = db.get_event_by_slug(conn, slug)
        except db.NotFound:
            ui.status_code(404)
            with page_frame("max-w-xl"):
                ui.label("No such event.")
                ui.link("← All events", "/admin")
            return None
        people = db.list_participants(conn, event.id)
        exclusions = db.list_exclusions(conn, event.id)
        feasibility = db.event_feasibility(conn, event.id)

    names = {p.id: p.name for p in people}
    here = f"/admin/e/{event.slug}"

    def reload() -> None:
        ui.navigate.to(here)

    ui.page_title(f"Admin · {event.title}")
    with page_frame("max-w-xl"):
        ui.link("← All events", "/admin").classes("text-sm")
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(event.title).classes("text-2xl font-bold")
            _status_badge(event)
        _share_link(event)

        _section("Settings")
        _settings_form(event, has_people=bool(people), reload=reload)

        _section(f"People ({len(people)})")
        _people_list(event, people, reload)

        _section("Exclusions")
        _exclusions(event, people, exclusions, names, reload)
        _feasibility_banner(feasibility, len(people), names, event)

        _section("Draw")
        _draw(event, len(people), len(exclusions), feasibility, names, reload)

        if event.is_open:
            _section("Danger zone")
            _delete_button(event)
    return None


def _share_link(event: db.Event) -> None:
    url = f"{get_settings().base_url}/e/{event.slug}"
    with ui.row().classes("w-full items-center gap-2"):
        ui.link(url, f"/e/{event.slug}", new_tab=True).classes("text-sm break-all")
        ui.button(
            "Copy link",
            on_click=lambda: (ui.clipboard.write(url), ui.notify("Link copied")),
        ).props("flat dense")


def _settings_form(event: db.Event, has_people: bool, reload) -> None:
    title = ui.input("Title", value=event.title).props("outlined").classes("w-full")
    budget = ui.number("Budget (S$)", value=event.budget, min=1, precision=0).props("outlined")
    if not event.is_open:
        budget.props("readonly")
        ui.label("🔒 Budget is fixed after the draw.").classes("text-xs text-gray-500 -mt-2")

    questions_locked = has_people or not event.is_open
    questions = (
        ui.textarea("Clue questions (one per line)", value="\n".join(event.questions))
        .props("outlined autogrow")
        .classes("w-full")
    )
    if questions_locked:
        questions.props("readonly")
        ui.label("🔒 Questions are locked because people have joined.").classes(
            "text-xs text-gray-500 -mt-2"
        )

    def save() -> None:
        amount = _whole_number(budget.value)
        if amount is None:
            ui.notify("Budget must be a whole number above 0.", type="warning")
            return
        new_questions = list(event.questions) if questions_locked else _lines(questions.value)
        try:
            with open_db() as conn:
                db.update_event(conn, event.id, title.value, amount, new_questions)
        except (db.DbError, ValueError) as exc:
            ui.notify(str(exc), type="negative")
            return
        # No reload: the fields already show what was saved, and a reload would hide this.
        ui.notify("Saved", type="positive")

    ui.button("Save settings", on_click=save).props("outline")


def _people_list(event: db.Event, people: list[db.Participant], reload) -> None:
    if not people:
        ui.label("Nobody has joined yet. Share the link!").classes("text-gray-600")
    for person in people:
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(f"{person.name} · “{person.nickname}”").classes("font-medium")
                ui.label(person.email).classes("text-xs text-gray-500 break-all")
            if event.is_open:

                async def remove(p: db.Participant = person) -> None:
                    if not await _confirm(
                        f"Remove {p.name}? Their sign-up and exclusions are deleted.", "Remove"
                    ):
                        return
                    try:
                        with open_db() as conn:
                            db.remove_participant(conn, p.id)
                    except db.DbError as exc:
                        ui.notify(str(exc), type="negative")
                        return
                    reload()

                ui.button(icon="close", on_click=remove).props("flat round dense color=negative")


def _exclusions(
    event: db.Event,
    people: list[db.Participant],
    exclusions: list[tuple[int, int]],
    names: dict[int, str],
    reload,
) -> None:
    if not exclusions:
        ui.label("None. Add couples so they don't get each other.").classes("text-gray-600")
    for a_id, b_id in exclusions:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"{names[a_id]} ✕ {names[b_id]}")
            if event.is_open:

                def remove(a: int = a_id, b: int = b_id) -> None:
                    try:
                        with open_db() as conn:
                            db.remove_exclusion(conn, event.id, a, b)
                    except db.DbError as exc:
                        ui.notify(str(exc), type="negative")
                        return
                    reload()

                ui.button(icon="delete", on_click=remove).props("flat round dense")

    if not event.is_open or len(people) < 2:
        return
    options = {p.id: f"{p.name} ({p.nickname})" for p in people}
    with ui.row().classes("w-full items-center gap-2 no-wrap"):
        first = ui.select(options, label="Person", with_input=True).classes("grow")
        second = ui.select(options, label="Person", with_input=True).classes("grow")

        def add() -> None:
            if first.value is None or second.value is None:
                ui.notify("Pick two people.", type="warning")
                return
            try:
                with open_db() as conn:
                    db.add_exclusion(conn, event.id, first.value, second.value)
            except (db.DbError, ValueError) as exc:
                ui.notify(str(exc), type="negative")
                return
            reload()

        ui.button("Add", on_click=add)


def _feasibility_banner(feasibility, count: int, names: dict[int, str], event: db.Event) -> None:
    if not event.is_open:
        return
    if count < 3:
        _banner("ℹ️ Matching needs at least 3 people.", "bg-gray-100")
    elif feasibility.verdict is Verdict.IMPOSSIBLE:
        stuck = ", ".join(names[i] for i in feasibility.stuck)
        _banner(
            f"❌ Matching is impossible: {stuck} can't be matched. Remove an exclusion "
            "involving them.",
            "bg-red-100",
        )
    elif feasibility.verdict is Verdict.GUARANTEED:
        _banner("✅ Matching will work.", "bg-green-100")
    else:
        _banner(
            "⚠️ The exclusions are tight; matching will probably work. Run it to find out.",
            "bg-amber-100",
        )


def _draw(
    event: db.Event,
    people: int,
    exclusions: int,
    feasibility,
    names: dict[int, str],
    reload,
) -> None:
    if not event.is_open:
        when = (event.matched_at or "")[:10]
        ui.label(f"✓ Matched on {when}. Everyone can see their giftee at the event link.")
        ui.label("Who got whom is secret, even from you. 🤫").classes("text-sm text-gray-500")
        return

    async def run() -> None:
        plural = "" if exclusions == 1 else "s"
        if not await _confirm(
            f"{people} people, {exclusions} exclusion{plural}. Draw now? Everyone will see "
            "their giftee, and sign-ups, answers and exclusions can't change after this.",
            "Draw now",
        ):
            return
        try:
            with open_db() as conn:
                db.run_matching(conn, event.id, random.SystemRandom())
        except MatchingError as exc:
            # Name people only when they're the cause, not for "need at least 3 people".
            who = ", ".join(names.get(i, "?") for i in exc.people) if people >= 3 else ""
            ui.notify(f"{exc} {who}".strip(), type="negative", multi_line=True, timeout=0)
            return
        except db.DbError as exc:
            ui.notify(str(exc), type="negative")
            return
        # The reloaded page shows "✓ Matched on …" (a toast here would vanish on reload).
        reload()

    can_run = people >= 3 and feasibility.verdict is not Verdict.IMPOSSIBLE
    button = ui.button("Run matching", on_click=run).props("color=positive").classes("w-full")
    if not can_run:
        button.disable()
        ui.label("Fix the problem above to enable the draw.").classes("text-xs text-gray-500 -mt-2")


def _delete_button(event: db.Event) -> None:
    async def delete() -> None:
        if not await _confirm(
            f"Delete “{event.title}” with all its sign-ups and exclusions?", "Delete"
        ):
            return
        try:
            with open_db() as conn:
                db.delete_event(conn, event.id)
        except db.DbError as exc:
            ui.notify(str(exc), type="negative")
            return
        ui.navigate.to("/admin")

    ui.button("Delete event", on_click=delete).props("flat color=negative")


# --- helpers ---------------------------------------------------------------------------------


async def _confirm(message: str, ok_label: str) -> bool:
    """Ask yes/no in a dialog (documented ui.dialog submit pattern)."""
    with ui.dialog() as dialog, ui.card():
        ui.label(message)
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(ok_label, on_click=lambda: dialog.submit(True))
    result = await dialog
    dialog.delete()
    return bool(result)


def _section(title: str) -> None:
    ui.separator()
    ui.label(title).classes("text-lg font-semibold")


def _banner(text: str, bg: str) -> None:
    ui.label(text).classes(f"w-full p-3 rounded {bg}")


def _status_badge(event: db.Event) -> None:
    if event.is_open:
        ui.badge("open", color="blue")
    else:
        ui.badge("matched", color="green")


def _lines(text: str | None) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _whole_number(value: float | None) -> int | None:
    if value is None or value < 1 or int(value) != value:
        return None
    return int(value)
