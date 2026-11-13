"""The event page /e/<slug>: one page whose content depends on who's looking.

States (worked out fresh from the database on every load):
  A. not logged in                → welcome + login form
  B. logged in, not joined, open  → sign-up form   (also C's "edit" mode: ?edit=1)
  C. joined, event open           → "you're in" + answers + edit button
  D. joined, event matched        → your giftee
  E. not joined, event matched    → sign-ups closed
After any change the page navigates to itself, so it always shows what the database says.
"""

from fastapi import Request
from nicegui import ui

from gift_exchange.core import db
from gift_exchange.ui.dbconn import open_db
from gift_exchange.ui.layout import account_footer, page_frame
from gift_exchange.ui.login import login_form
from gift_exchange.ui.session import current_email

MAX_NAME = 80
MAX_ANSWER = 500


@ui.page("/e/{slug}")
def event_page(slug: str, request: Request, edit: bool = False) -> None:
    """One event's page; what it shows depends on the viewer (see the module docstring).

    Args:
        slug: The event's URL slug (case is ignored).
        request: The incoming request (injected by NiceGUI), for the session cookie.
        edit: `?edit=true` reopens the sign-up form for someone who has already joined.
    """
    email = current_email(request)
    with open_db() as conn:
        try:
            event = db.get_event_by_slug(conn, slug)
        except db.NotFound:
            ui.status_code(404)
            with page_frame():
                ui.label("No such event 🤔").classes("theme-title text-xl font-semibold")
                ui.label("Check the link you were sent.")
            return
        count = db.count_participants(conn, event.id)
        me = _my_signup(conn, event.id, email)
        giftee = db.get_giftee(conn, event.id, email) if email and not event.is_open else None

    ui.page_title(event.title)
    with page_frame(theme=event.theme):
        _header(event, count)
        _how_it_works(event)
        if email is None:
            _welcome(event)
        elif event.is_open and (me is None or edit):
            _signup_form(event, email, me)
        elif event.is_open:
            _joined(event, me)
        elif giftee is not None:
            _giftee(event, giftee)
        else:
            _closed()
        if email:
            account_footer(email)


# --- states ------------------------------------------------------------------------------


def _welcome(event: db.Event) -> None:
    if not event.is_open:
        _closed()
        ui.label("Already joined? Log in to see your giftee.").classes("mt-2")
    login_form(f"/e/{event.slug}")


def _signup_form(event: db.Event, email: str, me: db.Participant | None) -> None:
    editing = me is not None
    ui.label("Edit your answers" if editing else "Join the gift exchange").classes(
        "theme-title text-lg font-semibold"
    )
    required = {"Required": lambda v: bool(v and v.strip())}

    name = (
        ui.input(
            "Your real name",
            value=me.name if me else "",
            validation={**required, "Too long": lambda v: len(v or "") <= MAX_NAME},
        )
        .props("outlined")
        .classes("w-full")
    )
    name.props["hint"] = "Only the organiser sees this (and everyone at the reveal)."
    nickname = (
        ui.input(
            "Nickname",
            value=me.nickname if me else "",
            validation={**required, "Too long": lambda v: len(v or "") <= MAX_NAME},
        )
        .props("outlined")
        .classes("w-full")
    )
    nickname.props["hint"] = "Your Santa sees this instead of your name. Keep it a mystery! 🕵️"

    answers = []
    for section in event.sections:
        _section_heading(section)
        for question in section.questions:
            i = len(answers)
            answers.append(
                ui.textarea(
                    question,
                    value=me.answers[i] if me else "",
                    validation={**required, "Too long": lambda v: len(v or "") <= MAX_ANSWER},
                )
                .props("outlined autogrow")
                .classes("w-full")
            )

    def submit() -> None:
        fields = [name, nickname, *answers]
        results = [f.validate() for f in fields]  # validate every field so all errors show
        if not all(results):
            ui.notify("Please fill in every field.", type="warning")
            return
        values = [a.value for a in answers]
        try:
            with open_db() as conn:
                if editing:
                    db.update_signup(conn, event.id, email, name.value, nickname.value, values)
                else:
                    db.join_event(conn, event.id, email, name.value, nickname.value, values)
        except (db.DbError, ValueError) as exc:
            ui.notify(str(exc), type="negative")
            return
        ui.navigate.to(f"/e/{event.slug}")

    with ui.row().classes("w-full gap-2"):
        ui.button("Save changes" if editing else "Join 🎁", on_click=submit).classes("grow")
        if editing:
            ui.button("Cancel", on_click=lambda: ui.navigate.to(f"/e/{event.slug}")).props("flat")


def _joined(event: db.Event, me: db.Participant) -> None:
    ui.label("You're in! 🎉").classes("theme-title text-lg font-semibold")
    ui.label("The draw happens soon. You can edit your answers until then.")
    with ui.card().classes("w-full").props("flat bordered"):
        _qa("Nickname", me.nickname)
        for section, pairs in db.pair_answers(event.sections, me.answers):
            _section_heading(section)
            for question, answer in pairs:
                _qa(question, answer)
    ui.button(
        "Edit my answers", on_click=lambda: ui.navigate.to(f"/e/{event.slug}?edit=true")
    ).props("outline").classes("w-full")


def _giftee(event: db.Event, giftee: db.Giftee) -> None:
    ui.label("You're Santa for…").classes("text-lg")
    ui.label(f"🎁 {giftee.nickname} 🎁").classes(
        "theme-title text-3xl font-bold text-center w-full my-2"
    )
    ui.label(f"Budget: S${giftee.budget}").classes("font-semibold")
    ui.label("What they told us:").classes("mt-2")
    with ui.card().classes("w-full").props("flat bordered"):
        for title, pairs in giftee.clues:
            if title:
                ui.label(title).classes("font-semibold mt-1")
            for question, answer in pairs:
                _qa(question, answer)
    ui.label("🤫 Keep it secret until the party!").classes("text-center w-full mt-2")


def _closed() -> None:
    ui.label("Sign-ups are closed. The draw has already happened.").classes("text-lg")


# --- layout helpers -------------------------------------------------------------------------


def _header(event: db.Event, count: int) -> None:
    ui.label(event.title).classes("theme-title text-2xl font-bold")
    joined = "Be the first to join!" if count == 0 else f"{count} joined"
    if not event.is_open:
        joined = f"{count} taking part"
    ui.label(f"Budget: S${event.budget} · {joined}").classes("text-gray-600 -mt-3")
    ui.separator()


def _how_it_works(event: db.Event) -> None:
    """The rules of the exchange, built from the event's settings (budget, sections)."""
    steps = [
        "**Sign up** with your real name, a secret nickname and answers to a few questions. "
        "Your answers are the clues for your Santa"
        + (" (you can edit them until the draw)." if event.is_open else "."),
        (
            "**The draw:** once everyone's in, the organiser runs it. Everyone becomes Santa for "
            "one other person, picked at random."
        ),
        (
            "**Your giftee:** this page then shows their nickname and clues, never their real "
            "name. Use the clues to pick a gift."
        ),
        f"**Budget:** about **S${event.budget}**.",
        (
            "**Keep it secret 🤫** At the party, gifts are handed over and everyone guesses who "
            "their Santa was. Nobody can see who got whom, not even the organiser."
        ),
    ]
    if any(section.hidden for section in event.sections):
        steps.append(
            "Answers marked 🤫 aren't shown to your Santa; they're saved for the party reveal."
        )
    ui.label("How it works").classes("theme-title text-lg font-semibold")
    ui.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))).classes("-mt-4")


def _section_heading(section: db.Section) -> None:
    if section.title:
        ui.label(section.title).classes("font-semibold mt-2")
    if section.hidden:
        ui.label("🤫 Your Santa won't see these; they're saved for the party reveal.").classes(
            "text-xs text-gray-500 -mt-3"
        )


def _qa(question: str, answer: str) -> None:
    ui.label(question).classes("text-sm text-gray-500")
    ui.label(answer or "—").classes("-mt-3 mb-1 whitespace-pre-wrap")


def _my_signup(conn, event_id: int, email: str | None) -> db.Participant | None:
    if email is None:
        return None
    try:
        return db.get_participant(conn, event_id, email)
    except db.NotFound:
        return None
