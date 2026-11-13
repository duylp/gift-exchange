-- Initial schema: events, participants, exclusions, matches.
-- No users table: a person is identified by email within each event (the login cookie holds
-- the signed email). Cross-event features can match on email.
-- All tables STRICT (SQLite enforces column types). Timestamps are UTC ISO-8601 text.

CREATE TABLE events (
    id         INTEGER PRIMARY KEY,
    -- lowercase letters, digits and hyphens, starting with a letter or digit (e.g. xmas-2026)
    slug       TEXT NOT NULL UNIQUE
               CHECK (slug GLOB '[a-z0-9]*' AND slug NOT GLOB '*[^a-z0-9-]*'),
    title      TEXT NOT NULL,
    budget     INTEGER NOT NULL CHECK (budget > 0),  -- whole S$
    -- JSON array of question sections [{"title", "questions": [...], "hidden"}]
    -- (core/db/models.py); locked once anyone has signed up (trigger below)
    questions  TEXT NOT NULL DEFAULT '[]'
               CHECK (json_valid(questions) AND json_type(questions) = 'array'),
    status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'matched')),
    -- look of the event page: a preset name (core/db/models.py THEMES, styled in
    -- ui/themes.py). No CHECK, so a new theme needs no migration; core/db validates on
    -- write, the UI falls back to 'plain'. Cosmetic: editable after matching.
    theme      TEXT NOT NULL DEFAULT 'plain',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    matched_at TEXT
) STRICT;

CREATE TABLE participants (
    id         INTEGER PRIMARY KEY,
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    email      TEXT NOT NULL COLLATE NOCASE,  -- lowercased; identifies the person (login)
    name       TEXT NOT NULL,                 -- real name (organiser view, reveal)
    nickname   TEXT NOT NULL COLLATE NOCASE,  -- anonymous name shown to their Santa
    -- JSON array of answer strings: every question across the sections, in order
    answers    TEXT NOT NULL DEFAULT '[]'
               CHECK (json_valid(answers) AND json_type(answers) = 'array'),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (event_id, email),      -- join an event once
    UNIQUE (event_id, nickname),   -- unambiguous for guess-your-Santa
    UNIQUE (event_id, id)          -- target for the same-event foreign keys below
) STRICT;

-- Two-way exclusion, stored once per pair with a_id < b_id.
CREATE TABLE exclusions (
    event_id INTEGER NOT NULL,
    a_id     INTEGER NOT NULL,
    b_id     INTEGER NOT NULL,
    PRIMARY KEY (a_id, b_id),
    CHECK (a_id < b_id),
    FOREIGN KEY (event_id, a_id) REFERENCES participants(event_id, id) ON DELETE CASCADE,
    FOREIGN KEY (event_id, b_id) REFERENCES participants(event_id, id) ON DELETE CASCADE
) STRICT;

-- No ON DELETE action: a matched participant (or their event) can't be deleted.
CREATE TABLE matches (
    event_id  INTEGER NOT NULL,
    giver_id  INTEGER PRIMARY KEY,
    giftee_id INTEGER NOT NULL UNIQUE,
    CHECK (giver_id <> giftee_id),
    FOREIGN KEY (event_id, giver_id)  REFERENCES participants(event_id, id),
    FOREIGN KEY (event_id, giftee_id) REFERENCES participants(event_id, id)
) STRICT;

CREATE INDEX participants_email ON participants(email);
CREATE INDEX exclusions_event ON exclusions(event_id);
CREATE INDEX matches_event ON matches(event_id);

-- Lifecycle rules, enforced by the database so an app bug can't break them.

CREATE TRIGGER events_questions_locked
BEFORE UPDATE OF questions ON events
WHEN NEW.questions IS NOT OLD.questions
 AND EXISTS (SELECT 1 FROM participants WHERE event_id = OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'questions are locked once someone has signed up');
END;

CREATE TRIGGER events_budget_fixed_after_match
BEFORE UPDATE OF budget ON events
WHEN OLD.status = 'matched' AND NEW.budget IS NOT OLD.budget
BEGIN
    SELECT RAISE(ABORT, 'the budget is fixed: the event has been matched');
END;

CREATE TRIGGER events_matched_is_final
BEFORE UPDATE OF status ON events
WHEN OLD.status = 'matched' AND NEW.status <> 'matched'
BEGIN
    SELECT RAISE(ABORT, 'a matched event cannot be reopened');
END;

CREATE TRIGGER participants_no_join_after_match
BEFORE INSERT ON participants
WHEN (SELECT status FROM events WHERE id = NEW.event_id) = 'matched'
BEGIN
    SELECT RAISE(ABORT, 'sign-ups are closed: the event has been matched');
END;

CREATE TRIGGER participants_no_edit_after_match
BEFORE UPDATE ON participants
WHEN (SELECT status FROM events WHERE id = OLD.event_id) = 'matched'
BEGIN
    SELECT RAISE(ABORT, 'sign-ups are closed: the event has been matched');
END;

CREATE TRIGGER exclusions_no_insert_after_match
BEFORE INSERT ON exclusions
WHEN (SELECT status FROM events WHERE id = NEW.event_id) = 'matched'
BEGIN
    SELECT RAISE(ABORT, 'exclusions are fixed: the event has been matched');
END;

CREATE TRIGGER exclusions_no_delete_after_match
BEFORE DELETE ON exclusions
WHEN (SELECT status FROM events WHERE id = OLD.event_id) = 'matched'
BEGIN
    SELECT RAISE(ABORT, 'exclusions are fixed: the event has been matched');
END;
