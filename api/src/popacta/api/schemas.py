"""Request and response schemas — the contract between `api/` and `web/`.

**Every endpoint declares a `response_model` built from these.** The 2025 app returned raw
SQLAlchemy objects, so client and server types drifted apart silently all season (LEG-7).
Request models set `extra="forbid"`, because a field the UI sends that the server does not
declare must be a 422 and not a silent drop — that is how `te_slots` became unsettable
(LEG-2).

These are also the shapes the UI narrates from. A recommendation row has to be explainable
on screen without a post-hoc gloss, so every number the screen shows is a field here.
"""

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BoardResponse",
    "DraftStateResponse",
    "HealthResponse",
    "PickRequest",
    "PickResponse",
    "PlayerSummary",
    "RecommendationRow",
    "RosterSlotView",
    "SeatRequest",
]


class _Strict(BaseModel):
    """Requests reject unknown fields. See LEG-2."""

    model_config = ConfigDict(extra="forbid")


class PlayerSummary(BaseModel):
    """Enough to render a player anywhere in the UI."""

    player_id: str
    name: str
    position: str
    team: str | None = None
    bye_week: int | None = None
    points: float


class RecommendationRow(BaseModel):
    """One board row, carrying every term needed to explain its own ranking.

    `survival`, `next_turn_baseline` and `plan` differ from `marginal_value` only once
    BLK-1 lands and survival probability comes online. Until then `plan == marginal_value`
    and `survival` is `null` — the UI must say so rather than imply a probability it does
    not have.
    """

    player: PlayerSummary
    marginal_value: float = Field(description="u(p|R): value added to your starting lineup")
    plan: float = Field(description="u(p|R) + B(p); equals marginal_value in degraded mode")
    cost_of_passing: float = Field(description="How much worse than the best available")
    next_turn_baseline: float
    survival: float | None = Field(default=None, description="null until BLK-1 lands")
    tier: int | None = None
    players_until_cliff: int | None = None
    slot_filled: str | None = None


class RosterSlotView(BaseModel):
    """A starter slot and who currently fills it."""

    slot_id: str
    slot_name: str
    eligible: list[str]
    player: PlayerSummary | None = None


class DraftStateResponse(BaseModel):
    """Where the draft is right now."""

    picks_made: int
    total_picks: int
    next_pick_number: int | None
    seat_on_the_clock: int | None
    my_seat: int
    is_my_turn: bool
    picks_until_my_turn: int | None
    my_roster: list[PlayerSummary]
    my_slots: list[RosterSlotView]


class BoardResponse(BaseModel):
    """The board plus the state it was computed against.

    Returned together deliberately: a board and a draft state fetched separately can
    disagree, and on draft night a stale board is worse than a slow one.
    """

    draft: DraftStateResponse
    recommendations: list[RecommendationRow]
    degraded: bool = Field(
        description="True while survival probability is unavailable (BLK-1). The UI must "
        "surface this — a board without survival is still useful, but it is not the "
        "next-pick-window model and must not claim to be."
    )
    degraded_reason: str | None = None


class PickRequest(_Strict):
    """Record a pick. Any team's pick, not just yours."""

    player_id: str


class PickResponse(BaseModel):
    pick_number: int
    round: int
    seat: int
    player: PlayerSummary | None = Field(
        default=None,
        description="null for a DEF or K pick — recorded because it consumes a pick and "
        "shifts next-turn maths, but never ranked.",
    )


class SeatRequest(_Strict):
    """Set which seat is yours.

    A parameter rather than a lookup because Sleeper's `draft_order` is still null
    (BLK-3). When it populates, this becomes a sync rather than an input.
    """

    seat: int = Field(ge=1)


class HealthResponse(BaseModel):
    status: str
    players_loaded: int
    degraded: bool
