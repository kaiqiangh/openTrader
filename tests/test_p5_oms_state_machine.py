from __future__ import annotations

import pytest

from services.oms.state_machine import (
    OMSStateMachine,
    OMSStateTransitionError,
    TERMINAL_STATES,
    transition_matrix,
)


def test_oms_state_machine_allows_nominal_lifecycle_sequence() -> None:
    machine = OMSStateMachine(initial_state="NEW")

    machine.apply("SUBMITTED")
    machine.apply("OPEN")
    machine.apply("PARTIALLY_FILLED")
    outcome = machine.apply("FILLED")

    assert outcome.changed is True
    assert outcome.previous_state == "PARTIALLY_FILLED"
    assert machine.current_state == "FILLED"


def test_oms_state_machine_rejects_invalid_transition() -> None:
    machine = OMSStateMachine(initial_state="NEW")

    with pytest.raises(OMSStateTransitionError):
        machine.apply("FILLED")


@pytest.mark.parametrize("terminal_state", sorted(TERMINAL_STATES))
def test_oms_state_machine_allows_idempotent_terminal_replay(terminal_state: str) -> None:
    machine = OMSStateMachine(initial_state=terminal_state)

    outcome = machine.apply(terminal_state)

    assert outcome.changed is False
    assert outcome.previous_state == terminal_state
    assert machine.current_state == terminal_state


def test_oms_state_machine_blocks_transition_from_terminal_to_open() -> None:
    machine = OMSStateMachine(initial_state="CANCELED")

    with pytest.raises(OMSStateTransitionError):
        machine.apply("OPEN")


def test_oms_state_machine_matrix_covers_required_states() -> None:
    matrix = transition_matrix()

    assert set(matrix) == {
        "NEW",
        "SUBMITTED",
        "OPEN",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELED",
        "REJECTED",
        "EXPIRED",
    }
    assert "SUBMITTED" in matrix["NEW"]
    assert "OPEN" in matrix["SUBMITTED"]
    assert "FILLED" in matrix["PARTIALLY_FILLED"]


def test_oms_state_machine_rejects_unknown_state() -> None:
    machine = OMSStateMachine()

    with pytest.raises(OMSStateTransitionError):
        machine.apply("UNKNOWN")
