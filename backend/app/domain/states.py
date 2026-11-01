from enum import StrEnum


class CampaignState(StrEnum):
    COLLECTING = "COLLECTING"
    PLANNING = "PLANNING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHING = "PUBLISHING"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    READY_PAUSED = "READY_PAUSED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


S = CampaignState
ALLOWED: dict[CampaignState, frozenset[CampaignState]] = {
    S.COLLECTING: frozenset({S.COLLECTING, S.PLANNING}),  # S2, S3
    S.PLANNING: frozenset({S.PLANNING, S.IN_REVIEW, S.COLLECTING}),  # S4, S5, S6
    S.IN_REVIEW: frozenset({S.PLANNING, S.APPROVED}),  # S7, S8
    S.APPROVED: frozenset({S.PLANNING, S.PUBLISHING}),  # S9, S10
    S.PUBLISHING: frozenset({S.PUBLISH_FAILED, S.READY_PAUSED}),  # S11, S14
    S.PUBLISH_FAILED: frozenset({S.PUBLISHING, S.IN_REVIEW}),  # S12, S13
    S.READY_PAUSED: frozenset({S.ACTIVE}),  # S15
    S.ACTIVE: frozenset({S.PAUSED, S.COMPLETED}),  # S16, S18
    S.PAUSED: frozenset({S.ACTIVE}),  # S17
    S.COMPLETED: frozenset(),
}


def can_transition(src: CampaignState, dst: CampaignState) -> bool:
    return dst in ALLOWED[src]


class ProposalState(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


P = ProposalState
PROPOSAL_ALLOWED: dict[ProposalState, frozenset[ProposalState]] = {
    P.PROPOSED: frozenset({P.APPROVED, P.REJECTED, P.EXPIRED}),  # P2, P3, P4
    P.APPROVED: frozenset({P.APPLIED, P.FAILED}),  # P5, P6
}
