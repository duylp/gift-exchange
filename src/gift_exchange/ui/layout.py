"""Shared page layout: a centred column with a link home at the top, styled by a theme."""

import random

from nicegui import ui

from gift_exchange.core import db
from gift_exchange.ui.themes import Theme, get_theme

# Small coloured drawings that fall with the snow (fixed constants, so no sanitising).
_CANE_SVG = """<svg viewBox="0 0 24 40" width="0.6em" height="1em">
<path d="M7 37V13a6 6 0 0 1 12 0v3" fill="none" stroke="#cbd5e1" stroke-width="6.5"
 stroke-linecap="round"/>
<path d="M7 37V13a6 6 0 0 1 12 0v3" fill="none" stroke="#fff" stroke-width="5"
 stroke-linecap="round"/>
<path d="M7 37V13a6 6 0 0 1 12 0v3" fill="none" stroke="#dc2626" stroke-width="5"
 stroke-dasharray="3 3"/>
</svg>"""

_SOCK_SVG = """<svg viewBox="0 0 32 40" width="0.8em" height="1em">
<path d="M8 9H20V24Q21 26 24 27L27 28Q31 30 29 34Q27 38 22 37L12 35Q8 34 8 29Z"
 fill="#dc2626"/>
<rect x="8" y="17" width="12" height="3" fill="#15803d"/>
<path d="M24 27L27 28Q31 30 29 34Q28 36 26 37Q28 32 24 27Z" fill="#15803d"/>
<path d="M8 27Q8 34 12 35L14 35Q10 32 8 27Z" fill="#15803d"/>
<rect x="6" y="4" width="16" height="7" rx="2" fill="#fff" stroke="#cbd5e1"/>
</svg>"""

# Falling items as (kind, centre %, fall seconds, delay seconds, size rem): fixed positions.
# Mostly snow, with a few socks and candy canes. Each starts at a random angle and turns
# steadily one way while falling (see `_apply`).
_FALLING = [
    ("flake", 3, 14, 0, 1.8),
    ("cane", 11, 18, 6, 5.2),
    ("flake", 19, 12, 3, 2.2),
    ("sock", 27, 16, 9, 5.2),
    ("flake", 35, 20, 1, 1.2),
    ("flake", 43, 13, 7, 2.0),
    ("cane", 51, 17, 4, 5.2),
    ("flake", 59, 15, 11, 1.8),
    ("sock", 67, 19, 2, 5.2),
    ("flake", 75, 12, 8, 2.2),
    ("cane", 83, 16, 5, 5.2),
    ("flake", 91, 14, 10, 1.4),
    ("sock", 97, 18, 3, 5.2),
]

_SNOW_CSS = """
.theme-snow { position: fixed; inset: 0; pointer-events: none; overflow: hidden; z-index: 0; }
.theme-snow > * {
    position: absolute; top: -8rem; line-height: 1;
    animation: theme-fall linear infinite; --tilt: 0deg; --spin: 180deg;
}
.theme-snow > .theme-flake { color: #94a3b8; opacity: 0.55; }
.theme-snow > .theme-toy { opacity: 0.8; }
.theme-snow svg { display: block; }
@keyframes theme-fall {
    from { transform: translateY(0) rotate(var(--tilt)); }
    to { transform: translateY(calc(100vh + 16rem)) rotate(calc(var(--tilt) + var(--spin))); }
}
@media (prefers-reduced-motion: reduce) { .theme-snow { display: none; } }
"""

_STRIPE_CSS = """
.theme-stripe {
    height: 6px; border-radius: 3px;
    background: repeating-linear-gradient(-45deg, #b91c1c 0 10px, #ffffff 10px 20px);
}
"""


def page_frame(max_width: str = "max-w-md", theme: str = db.DEFAULT_THEME) -> ui.column:
    """The column every page builds into, starting with a link home to `/`.

    Use as `with page_frame(): ...`.

    Args:
        max_width: Tailwind max-width class for the column (wider for admin pages).
        theme: Name of the theme to style the page with (see `ui/themes.py`); unknown
            names fall back to `db.DEFAULT_THEME`.
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
    """Page-wide styling for a theme: colours, background, fonts, falling snow and toys."""
    if look.colors:
        ui.colors(**look.colors)
    if look.background:
        ui.query("body").style(f"background: {look.background}")
    _add_fonts(look)
    if look.stripe:
        ui.add_css(_STRIPE_CSS)
    if look.snow:
        ui.add_css(_SNOW_CSS)
        with ui.element("div").classes("theme-snow").props('aria-hidden="true"'):
            for kind, left, fall, delay, size in _FALLING:
                if kind == "flake":
                    item = ui.label("❄").classes("theme-flake")
                else:
                    svg = _SOCK_SVG if kind == "sock" else _CANE_SVG
                    item = ui.html(svg, sanitize=False).classes("theme-toy")
                # Random start angle, then a steady turn one way (180–360°, either direction)
                # for the whole fall; new values on every page load.
                spin = random.choice((-1, 1)) * random.randint(180, 360)
                item.style(f"--tilt: {random.randint(-180, 180)}deg; --spin: {spin}deg")
                item.style(
                    f"left: calc({left}% - {size / 2}rem); font-size: {size}rem; "
                    f"animation-duration: {fall}s; animation-delay: -{delay}s"
                )


def _add_fonts(look: Theme) -> None:
    """Load the theme's Google Fonts (one request) and apply them."""
    families = []
    if look.body_font:
        families.append(f"family={look.body_font.replace(' ', '+')}:wght@400;600;700")
        ui.add_css(f"body {{ font-family: '{look.body_font}', sans-serif; }}")
    if look.title_font:
        families.append(f"family={look.title_font.replace(' ', '+')}:wght@700")
        ui.add_css(f".theme-title {{ font-family: '{look.title_font}', cursive; }}")
    if families:
        ui.add_head_html(
            '<link rel="stylesheet" '
            f'href="https://fonts.googleapis.com/css2?{"&".join(families)}&display=swap">'
        )


def account_footer(email: str) -> None:
    """The "Logged in as … · Log out" line at the bottom of a page."""
    ui.separator().classes("mt-4")
    with ui.row().classes("w-full justify-between text-sm text-gray-500"):
        ui.label(f"Logged in as {email}")
        ui.link("Log out", "/logout")
