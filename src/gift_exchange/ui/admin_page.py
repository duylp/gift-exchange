"""Organiser pages: /admin (events + create) and /admin/e/<slug> (manage one event).

Only emails in ADMIN_EMAILS get in. Like the event page, everything is read fresh from the
database on each load and every change navigates back to the page.

Match secrecy: these pages never show who got whom — only counts.
"""

import random
from collections.abc import Callable, Sequence

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
from gift_exchange.ui.themes import theme_options


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
    slug.props["hint"] = "Lowercase letters, digits and hyphens."
    title = (
        ui.input("Title", validation={"Required": lambda v: bool(v and v.strip())})
        .props("outlined")
        .classes("w-full")
    )
    budget = ui.number("Budget (S$)", value=30, min=1, precision=0).props("outlined")
    theme = _theme_select(db.DEFAULT_THEME)
    get_sections = _question_editor([])

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
                    get_sections(),
                    theme.value,
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
        guesses = db.count_guesses(conn, event.id)

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

        if not event.is_open:
            _section("Guesses")
            _guesses(event, guesses, len(people), reload)

        if event.is_open:
            _section("Danger zone")
            _delete_button(event)
    return None


def _theme_select(value: str) -> ui.select:
    select = ui.select(theme_options(), value=value, label="Theme").props("outlined")
    select.classes("w-full")
    select.props["hint"] = "Look of the event page. Can change any time."
    return select


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
        budget.props["hint"] = "🔒 Budget is fixed after the draw."
    theme = _theme_select(event.theme)

    questions_locked = has_people or not event.is_open
    if questions_locked:
        _question_list(event.sections)
    else:
        get_sections = _question_editor(event.sections)

    def save() -> None:
        amount = _whole_number(budget.value)
        if amount is None:
            ui.notify("Budget must be a whole number above 0.", type="warning")
            return
        new_sections = None if questions_locked else get_sections()  # None: keep them
        try:
            with open_db() as conn:
                try:
                    db.update_event(conn, event.id, title.value, amount, new_sections, theme.value)
                except db.QuestionsLocked:
                    # Someone joined since the page loaded: save the rest, keep the questions.
                    db.update_event(conn, event.id, title.value, amount, None, theme.value)
                    ui.notify(
                        "Saved, except the questions: someone has joined, so they're locked.",
                        type="warning",
                    )
                    ui.timer(3, reload, once=True)  # then show the locked questions
                    return
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
                # Never show nicknames here: the admin may be a participant, and nickname →
                # name would tell them who their giftee is (a test enforces this).
                ui.label(person.name).classes("font-medium")
                ui.label(person.email).classes("text-xs text-gray-500 break-all")
            if event.is_open:

                async def remove(p: db.Participant = person) -> None:
                    if not await _confirm(
                        f"Remove {p.name}? Their sign-up and exclusions are deleted.",
                        "Remove",
                        danger=True,
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
    # Names only (no nicknames, see _people_list); the email tells apart people who share a name.
    shared = {p.name for p in people if sum(q.name == p.name for q in people) > 1}
    options = {p.id: f"{p.name} ({p.email})" if p.name in shared else p.name for p in people}
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


def _guesses(event: db.Event, guessed: int, people: int, reload) -> None:
    """How many Santas have guessed their giftee, and the button to close guessing.

    Only the count: never who guessed whom (the admin may be a participant too).
    """
    ui.label(f"{guessed} of {people} have guessed who their giftee is.")
    if not event.guessing_open:
        when = (event.guesses_closed_at or "")[:10]
        ui.label(f"🔒 Guessing closed on {when}.").classes("text-sm text-gray-500")
        return

    async def close() -> None:
        if not await _confirm(
            f"Close guessing? {guessed} of {people} have guessed. Nobody can guess or "
            "change their guess after this.",
            "Close guesses",
            danger=True,
        ):
            return
        try:
            with open_db() as conn:
                db.close_guessing(conn, event.id)
        except db.DbError as exc:
            ui.notify(str(exc), type="negative")
            return
        reload()

    ui.button("Close guesses", on_click=close).props("outline").classes("w-full")
    ui.label("Do this at the party, just before the reveal.").classes("text-xs text-gray-500 -mt-2")


def _delete_button(event: db.Event) -> None:
    async def delete() -> None:
        if not await _confirm(
            f"Delete “{event.title}”? Its page and sign-ups disappear from the app "
            "(they're kept in the database and can be restored there).",
            "Delete",
            danger=True,
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


# --- clue questions ---------------------------------------------------------------------------


def _question_editor(initial: Sequence[db.Section]) -> Callable[[], list[db.Section]]:
    """Editable clue questions, grouped in sections (one box per question).

    Sections and questions can be added, reordered and removed; Enter in a question adds
    one below it. A section can be hidden from Santas (kept for the party reveal). The draft
    lives in a local variable only while the form is open; nothing is saved until the
    form's own button is pressed.

    Args:
        initial: The sections to start with, in order (none → one empty section).

    Returns:
        A function giving the current sections, for the save handler to call (the db
        layer drops blank questions and empty sections).
    """
    sections = [
        {"title": s.title, "hidden": s.hidden, "questions": list(s.questions)} for s in initial
    ] or [{"title": "", "hidden": False, "questions": []}]
    focus: list[tuple[int, int] | None] = [None]  # question box to focus after a refresh

    def add_question(si: int, qi: int) -> None:
        sections[si]["questions"].insert(qi, "")
        focus[0] = (si, qi)
        rows.refresh()

    def remove_question(si: int, qi: int) -> None:
        del sections[si]["questions"][qi]
        rows.refresh()

    def move_question(si: int, qi: int, step: int) -> None:
        _swap(sections[si]["questions"], qi, qi + step)
        rows.refresh()

    def add_section() -> None:
        sections.append({"title": "", "hidden": False, "questions": []})
        rows.refresh()

    def remove_section(si: int) -> None:
        del sections[si]
        rows.refresh()

    def move_section(si: int, step: int) -> None:
        _swap(sections, si, si + step)
        rows.refresh()

    ui.label("Clue questions").classes("font-medium")
    ui.label("Everyone answers these when they join; their Santa sees the answers.").classes(
        "text-xs text-gray-500 -mt-3"
    )

    @ui.refreshable
    def rows() -> None:
        number = 0
        for si, section in enumerate(sections):
            with ui.card().classes("w-full gap-2").props("flat bordered"):
                with ui.row().classes("w-full items-center no-wrap gap-0"):
                    ui.input(
                        placeholder="Section title (optional), e.g. About you",
                        value=section["title"],
                        on_change=lambda e, s=section: s.__setitem__("title", e.value),
                    ).props("dense").classes("grow font-semibold")
                    _move_remove_buttons(
                        len(sections),
                        si,
                        lambda step, si=si: move_section(si, step),
                        lambda si=si: remove_section(si),
                        "section",
                    )
                ui.switch(
                    "Hide from Santa (saved for the reveal)",
                    value=section["hidden"],
                    on_change=lambda e, s=section: s.__setitem__("hidden", e.value),
                ).props("dense").classes("text-sm")

                questions = section["questions"]
                for qi, text in enumerate(questions):
                    number += 1
                    with ui.row().classes("w-full items-center no-wrap gap-0"):
                        # A growing textarea so long questions wrap; Enter still adds the
                        # next question (.prevent: no newline in the box).
                        box = (
                            ui.textarea(
                                placeholder=f"Question {number}",
                                value=text,
                                on_change=lambda e, q=questions, qi=qi: q.__setitem__(qi, e.value),
                            )
                            .props(f'outlined dense autogrow rows=1 prefix="{number}."')
                            .classes("grow")
                            .on(
                                "keydown.enter.prevent",
                                lambda si=si, qi=qi: add_question(si, qi + 1),
                            )
                        )
                        if focus[0] == (si, qi):
                            box.props("autofocus")
                        _move_remove_buttons(
                            len(questions),
                            qi,
                            lambda step, si=si, qi=qi: move_question(si, qi, step),
                            lambda si=si, qi=qi: remove_question(si, qi),
                            "question",
                        )
                ui.button(
                    "Add question",
                    icon="add",
                    on_click=lambda si=si, q=questions: add_question(si, len(q)),
                ).props("flat dense")
        focus[0] = None
        ui.button("Add section", icon="playlist_add", on_click=add_section).props("outline dense")

    rows()
    return lambda: [db.Section(s["title"], tuple(s["questions"]), s["hidden"]) for s in sections]


def _move_remove_buttons(count: int, index: int, move, remove, what: str) -> None:
    """↑ ↓ ✕ buttons for item `index` of `count`; `move` gets -1 or +1."""
    up = ui.button(icon="arrow_upward", on_click=lambda: move(-1))
    up.props("flat round dense size=sm").tooltip(f"Move {what} up")
    down = ui.button(icon="arrow_downward", on_click=lambda: move(1))
    down.props("flat round dense size=sm").tooltip(f"Move {what} down")
    ui.button(icon="close", on_click=remove).props(
        "flat round dense size=sm color=negative"
    ).tooltip(f"Remove {what}")
    if index == 0:
        up.disable()
    if index == count - 1:
        down.disable()


def _swap(items: list, i: int, j: int) -> None:
    items[i], items[j] = items[j], items[i]


def _question_list(sections: Sequence[db.Section]) -> None:
    """Read-only view of an event's locked questions, by section."""
    ui.label("Clue questions").classes("font-medium")
    if not sections:
        ui.label("None.").classes("text-sm text-gray-600")
    number = 0
    for section in sections:
        if section.title or section.hidden:
            hidden = " 🤫 hidden from Santa" if section.hidden else ""
            ui.label(f"{section.title or 'Untitled'}{hidden}").classes("text-sm font-semibold")
        for q in section.questions:
            number += 1
            ui.label(f"{number}. {q}").classes("text-sm")
    ui.label("🔒 Questions are locked because people have joined.").classes("text-xs text-gray-500")


# --- helpers ---------------------------------------------------------------------------------


async def _confirm(message: str, ok_label: str, danger: bool = False) -> bool:
    """Ask yes/no in a dialog (documented ui.dialog submit pattern).

    Args:
        message: The question.
        ok_label: Text of the confirm button.
        danger: Show the confirm button in red (removing or deleting something).
    """
    with ui.dialog() as dialog, ui.card():
        ui.label(message)
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
            ok = ui.button(ok_label, on_click=lambda: dialog.submit(True))
            if danger:
                ok.props("color=negative")
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


def _whole_number(value: float | None) -> int | None:
    if value is None or value < 1 or int(value) != value:
        return None
    return int(value)
