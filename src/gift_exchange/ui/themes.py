"""How each event theme looks. The theme names live in `db.THEMES`; this maps them to styles.

A theme is applied per page by `layout.page_frame(theme=...)`. Only the event page uses the
event's theme; every other page is "plain".
"""

from dataclasses import dataclass, field

from gift_exchange.core import db


@dataclass(frozen=True)
class Theme:
    """The look of a page.

    Attributes:
        label: Name shown in the admin theme dropdown.
        colors: Quasar colours for `ui.colors` (buttons, inputs, toggles); empty = defaults.
        header: Text of the link home at the top of the page.
        background: CSS `background` for the page body, or None for the default.
        title_font: Google Fonts family for the event title (class `theme-title`), or None.
        card: Put the page content on a white rounded card (readable over a background).
        stripe: Candy-cane stripe under the header.
        snow: Gently falling snowflakes behind the content (off for reduced motion).
    """

    label: str
    colors: dict[str, str] = field(default_factory=dict)
    header: str = "🎁 Gift exchange"
    background: str | None = None
    title_font: str | None = None
    card: bool = False
    stripe: bool = False
    snow: bool = False


THEMES: dict[str, Theme] = {
    "plain": Theme("Plain"),
    "christmas": Theme(
        "Christmas 🎄",
        colors={"primary": "#15803d", "secondary": "#b91c1c", "accent": "#ca8a04"},
        header="🎄 Gift exchange 🎁",
        background="linear-gradient(180deg, #fdf2f2 0%, #f0f7f1 100%) fixed",
        title_font="Mountains of Christmas",
        card=True,
        stripe=True,
        snow=True,
    ),
}

assert set(THEMES) == set(db.THEMES), "ui/themes.py must style exactly db.THEMES"


def get_theme(name: str) -> Theme:
    """The theme called `name`, or "plain" if there is no such theme."""
    return THEMES.get(name, THEMES["plain"])


def theme_options() -> dict[str, str]:
    """Theme name → label, in `db.THEMES` order, for a `ui.select`."""
    return {name: THEMES[name].label for name in db.THEMES}
