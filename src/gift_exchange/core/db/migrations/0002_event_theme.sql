-- Per-event look (colours, header, decorations). The value names a preset defined in code
-- (core/db/models.py THEMES, styled in ui/themes.py). No CHECK on the allowed names, so a
-- new theme needs no migration; core/db validates on write, the UI falls back to 'plain'.
-- Cosmetic, so it stays editable after matching (no trigger).

ALTER TABLE events ADD COLUMN theme TEXT NOT NULL DEFAULT 'plain';
