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


class DuplicatePickError(DraftError):
    """A player already off the board was drafted again."""


class DraftCompleteError(DraftError):
    """A pick was recorded after every pick in the draft was already made."""


class NoSuchPickError(DraftError):
    """An undo referenced a pick number that has not been made."""
