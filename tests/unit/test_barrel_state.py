"""The allowed-transition table must match CLAUDE.md ch. 6 exactly."""

import pytest

from app.models import BarrelStatus as S
from app.services.barrel_state import NOT_ISSUABLE, TRANSITIONS, can_transition

SPEC = {
    S.IN_STOCK: {S.ON_LOAN, S.DAMAGED, S.LOST, S.WRITTEN_OFF},
    S.ON_LOAN: {S.IN_STOCK, S.DAMAGED, S.LOST, S.RETIRED},
    S.DAMAGED: {S.WRITTEN_OFF},
    S.LOST: {S.IN_STOCK, S.WRITTEN_OFF},
    S.RETIRED: {S.WRITTEN_OFF},
    S.WRITTEN_OFF: set(),
}


def test_transition_table_matches_specification() -> None:
    assert {k: set(v) for k, v in TRANSITIONS.items()} == SPEC
    assert set(TRANSITIONS) == set(S)


@pytest.mark.parametrize("from_status", list(S))
@pytest.mark.parametrize("to_status", list(S))
def test_can_transition_follows_the_table(from_status: S, to_status: S) -> None:
    assert can_transition(from_status, to_status) == (to_status in SPEC[from_status])


def test_written_off_is_final() -> None:
    assert not TRANSITIONS[S.WRITTEN_OFF]


def test_not_issuable_statuses() -> None:
    assert NOT_ISSUABLE == {S.DAMAGED, S.LOST, S.RETIRED, S.WRITTEN_OFF}
    assert S.IN_STOCK not in NOT_ISSUABLE
