from app.domain.ad_states import EDITABLE, AdState, can_transition

S = AdState


def test_publish_flow_is_allowed():
    path = [S.DRAFT, S.PUBLISHING, S.ACTIVE, S.PAUSED, S.ACTIVE, S.COMPLETED]
    assert all(can_transition(a, b) for a, b in zip(path, path[1:], strict=False))


def test_failed_publish_can_resume_or_be_discarded():
    assert can_transition(S.PUBLISHING, S.PUBLISH_FAILED)
    assert can_transition(S.PUBLISH_FAILED, S.PUBLISHING)
    assert can_transition(S.PUBLISH_FAILED, S.DRAFT)


def test_illegal_moves_are_refused():
    assert not can_transition(S.DRAFT, S.ACTIVE)
    assert not can_transition(S.PAUSED_ON_META, S.DRAFT)
    assert not can_transition(S.COMPLETED, S.ACTIVE)


def test_only_drafts_are_editable():
    assert EDITABLE == {S.DRAFT}
