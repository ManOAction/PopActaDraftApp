"""Domain exceptions.

One shared hierarchy so callers can catch `DraftError` broadly, and so the wave-1 modules
do not each invent their own. Every message must name the offending value — on draft night
the exception text is the entire debugging session.
"""


class DraftError(Exception):
    """Base class for every domain-level failure."""


class DraftRangeError(DraftError, ValueError):
    """A seat, round, or pick number fell outside its valid range.

    Subclasses `ValueError` so existing `except ValueError` handlers still behave.
    """


class LeagueConfigError(DraftError, ValueError):
    """The league or draft payload could not be turned into a usable configuration.

    Raised for an unrecognised roster slot, a non-snake draft, a structural value out of
    range, or the two Sleeper payloads disagreeing with each other. These are all "the
    league changed underneath us" failures, and they must surface at import time — days
    before the draft — rather than as a wrong number during it.

    Subclasses `ValueError` so existing `except ValueError` handlers still behave.
    """


class ImportDataError(DraftError, ValueError):
    """A source file could not be parsed into usable data.

    Raised by the ingest layer for an unexpected column layout, an unparseable value, a
    player that resolves to no Sleeper id or to several, or a file that fails an
    integrity check (for example a rankings export that turns out not to be superflex).

    Every one of these must surface at **import** time, days before the draft. LEG-4
    shipped because a parse failure was caught and defaulted to `0`.
    """


class InvalidPlayerError(DraftError, ValueError):
    """A player id or position was not usable.

    Covers a missing or non-string player id, and a roster entry whose position is not a
    `Position` member. The 2025 app absorbed values like these and produced wrong numbers
    rather than an error (LEG-4).
    """


class DuplicatePickError(DraftError):
    """A player already off the board was drafted again."""


class DraftCompleteError(DraftError):
    """A pick was recorded after every pick in the draft was already made."""


class NoSuchPickError(DraftError):
    """An undo referenced a pick number that has not been made."""
