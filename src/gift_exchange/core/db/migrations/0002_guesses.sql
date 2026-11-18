-- Giftee guesses: after matching, each Santa guesses which participant (real name) is
-- behind their giftee's nickname, for the party reveal. The organiser closes guessing.
--
-- Match secrecy: this table never refers to `matches`, and nothing checks a guess against
-- the matches before the reveal (scoring is designed later, with the reveal page).

-- When the organiser closed guessing (UTC ISO-8601), or NULL while guesses are open.
-- Only a matched event can close guessing, and closing is final (triggers below).
ALTER TABLE events ADD COLUMN guesses_closed_at TEXT;

-- One guess per Santa, overwritten on change.
CREATE TABLE guesses (
    event_id   INTEGER NOT NULL,
    guesser_id INTEGER PRIMARY KEY,   -- the Santa
    guessed_id INTEGER NOT NULL,      -- who they think their giftee really is
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (guesser_id <> guessed_id),
    -- No ON DELETE action: matched participants can't be deleted anyway.
    FOREIGN KEY (event_id, guesser_id) REFERENCES participants(event_id, id),
    FOREIGN KEY (event_id, guessed_id) REFERENCES participants(event_id, id)
) STRICT;

CREATE INDEX guesses_event ON guesses(event_id);

-- Guessing is allowed only after matching and until the organiser closes it.

CREATE TRIGGER guesses_insert_only_while_open
BEFORE INSERT ON guesses
WHEN NOT EXISTS (
    SELECT 1 FROM events
    WHERE id = NEW.event_id AND status = 'matched' AND guesses_closed_at IS NULL
)
BEGIN
    SELECT RAISE(ABORT, 'guessing is not open');
END;

CREATE TRIGGER guesses_update_only_while_open
BEFORE UPDATE ON guesses
WHEN NOT EXISTS (
    SELECT 1 FROM events
    WHERE id = NEW.event_id AND status = 'matched' AND guesses_closed_at IS NULL
)
OR NEW.event_id IS NOT OLD.event_id
BEGIN
    SELECT RAISE(ABORT, 'guessing is not open');
END;

CREATE TRIGGER guesses_no_delete_after_close
BEFORE DELETE ON guesses
WHEN (SELECT guesses_closed_at FROM events WHERE id = OLD.event_id) IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'guessing is closed');
END;

CREATE TRIGGER events_guesses_close_after_match
BEFORE UPDATE OF guesses_closed_at ON events
WHEN NEW.guesses_closed_at IS NOT NULL AND NEW.status <> 'matched'
BEGIN
    SELECT RAISE(ABORT, 'guessing can only close after matching');
END;

CREATE TRIGGER events_guesses_closed_is_final
BEFORE UPDATE OF guesses_closed_at ON events
WHEN OLD.guesses_closed_at IS NOT NULL AND NEW.guesses_closed_at IS NOT OLD.guesses_closed_at
BEGIN
    SELECT RAISE(ABORT, 'guessing is closed for good');
END;
