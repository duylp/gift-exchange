"""Shared page layout: a centred column with a link home at the top, styled by a theme."""

from nicegui import ui

from gift_exchange.ui.themes import Theme, get_theme

# Snowflakes as (left %, fall seconds, delay seconds, size rem): fixed, so no randomness.
_FLAKES = [
    (3, 14, 0, 0.9),
    (11, 18, 6, 0.7),
    (19, 12, 3, 1.1),
    (27, 16, 9, 0.8),
    (35, 20, 1, 0.6),
    (43, 13, 7, 1.0),
    (51, 17, 4, 0.7),
    (59, 15, 11, 0.9),
    (67, 19, 2, 0.6),
    (75, 12, 8, 1.1),
    (83, 16, 5, 0.8),
    (91, 14, 10, 0.7),
    (97, 18, 3, 0.9),
]

_SNOW_CSS = """
.theme-snow { position: fixed; inset: 0; pointer-events: none; overflow: hidden; z-index: 0; }
.theme-snow > * {
    position: absolute; top: -2rem; color: #94a3b8; opacity: 0.55;
    animation: theme-fall linear infinite;
}
@keyframes theme-fall {
    to { transform: translateY(calc(100vh + 4rem)) rotate(180deg); }
}
@media (prefers-reduced-motion: reduce) { .theme-snow { display: none; } }
"""

_STRIPE_CSS = """
.theme-stripe {
    height: 6px; border-radius: 3px;
    background: repeating-linear-gradient(-45deg, #b91c1c 0 10px, #ffffff 10px 20px);
}
"""


def page_frame(max_width: str = "max-w-md", theme: str = "plain") -> ui.column:
    """The column every page builds into, starting with a link home to `/`.

    Use as `with page_frame(): ...`.

    Args:
        max_width: Tailwind max-width class for the column (wider for admin pages).
        theme: Name of the theme to style the page with (see `ui/themes.py`). Only the
            event page passes the event's theme; unknown names fall back to "plain".
    """
    look = get_theme(theme)
    _apply(look)
    classes = f"w-full {max_width} mx-auto gap-4 p-4"
    if look.card:
        classes += " relative z-10 bg-white rounded-2xl shadow-md my-4"
    frame = ui.column().classes(classes)
    with frame:
        ui.link(look.header, "/").classes(
            "text-sm font-semibold text-gray-600 no-underline hover:underline"
        )
        if look.stripe:
            ui.element("div").classes("theme-stripe w-full -mt-2")
    return frame


def _apply(look: Theme) -> None:
    """Page-wide styling for a theme: colours, background, title font, snow."""
    if look.colors:
        ui.colors(**look.colors)
    if look.background:
        ui.query("body").style(f"background: {look.background}")
    if look.title_font:
        family = look.title_font.replace(" ", "+")
        ui.add_head_html(
            '<link rel="stylesheet" '
            f'href="https://fonts.googleapis.com/css2?family={family}:wght@700&display=swap">'
        )
        ui.add_css(f".theme-title {{ font-family: '{look.title_font}', cursive; }}")
    if look.stripe:
        ui.add_css(_STRIPE_CSS)
    if look.snow:
        ui.add_css(_SNOW_CSS)
        with ui.element("div").classes("theme-snow").props('aria-hidden="true"'):
            for left, fall, delay, size in _FLAKES:
                ui.label("❄").style(
                    f"left: {left}%; font-size: {size}rem; "
                    f"animation-duration: {fall}s; animation-delay: -{delay}s"
                )


def account_footer(email: str) -> None:
    """The "Logged in as … · Log out" line at the bottom of a page."""
    ui.separator().classes("mt-4")
    with ui.row().classes("w-full justify-between text-sm text-gray-500"):
        ui.label(f"Logged in as {email}")
        ui.link("Log out", "/logout")
