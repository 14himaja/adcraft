from enum import StrEnum


class AdState(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHING = "PUBLISHING"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    PAUSED_ON_META = "PAUSED_ON_META"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


S = AdState
ALLOWED: dict[AdState, frozenset[AdState]] = {
    S.DRAFT: frozenset({S.PUBLISHING}),
    S.PUBLISHING: frozenset({S.ACTIVE, S.PUBLISH_FAILED}),
    S.PUBLISH_FAILED: frozenset({S.PUBLISHING, S.DRAFT}),  # resume, discard
    S.PAUSED_ON_META: frozenset({S.ACTIVE}),
    S.ACTIVE: frozenset({S.PAUSED, S.COMPLETED}),
    S.PAUSED: frozenset({S.ACTIVE, S.COMPLETED}),
    S.COMPLETED: frozenset(),
}
EDITABLE = frozenset({S.DRAFT})


def can_transition(src: AdState, dst: AdState) -> bool:
    return dst in ALLOWED[src]
