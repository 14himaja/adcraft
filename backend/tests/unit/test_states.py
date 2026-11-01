import pytest

from app.domain.states import ALLOWED, can_transition
from app.domain.states import CampaignState as S

HAPPY_PATH = [
    S.COLLECTING,
    S.PLANNING,
    S.IN_REVIEW,
    S.APPROVED,
    S.PUBLISHING,
    S.READY_PAUSED,
    S.ACTIVE,
    S.COMPLETED,
]


def test_happy_path_is_allowed():
    assert all(can_transition(a, b) for a, b in zip(HAPPY_PATH, HAPPY_PATH[1:], strict=False))


@pytest.mark.parametrize(
    "src,dst",
    [
        (S.IN_REVIEW, S.PUBLISHING),  # skip approval
        (S.PLANNING, S.APPROVED),  # approve without review
        (S.APPROVED, S.ACTIVE),  # activate without publishing
        (S.COLLECTING, S.IN_REVIEW),  # review without a plan
        (S.READY_PAUSED, S.COMPLETED),
    ],
)
def test_shortcuts_are_forbidden(src, dst):
    assert not can_transition(src, dst)


def test_completed_is_terminal():
    assert ALLOWED[S.COMPLETED] == frozenset()


def test_every_state_has_an_entry():
    assert set(ALLOWED) == set(S)


def test_table_has_the_17_transitions_from_the_hld():
    assert sum(len(targets) for targets in ALLOWED.values()) == 17
