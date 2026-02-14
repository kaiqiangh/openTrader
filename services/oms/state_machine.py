from __future__ import annotations

from dataclasses import dataclass
from typing import Final

OMS_STATES: Final[tuple[str, ...]] = (
    "NEW",
    "SUBMITTED",
    "OPEN",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELED",
    "REJECTED",
    "EXPIRED",
)

TERMINAL_STATES: Final[frozenset[str]] = frozenset({"FILLED", "CANCELED", "REJECTED", "EXPIRED"})

_ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "NEW": frozenset({"SUBMITTED", "REJECTED", "CANCELED", "EXPIRED"}),
    "SUBMITTED": frozenset({"OPEN", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"}),
    "OPEN": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED"}),
    "PARTIALLY_FILLED": frozenset({"FILLED", "CANCELED", "EXPIRED"}),
    "FILLED": frozenset(),
    "CANCELED": frozenset(),
    "REJECTED": frozenset(),
    "EXPIRED": frozenset(),
}


class OMSStateTransitionError(ValueError):
    """Raised when an order state transition is invalid."""


@dataclass(frozen=True, slots=True)
class OMSStateTransition:
    previous_state: str
    current_state: str
    changed: bool


class OMSStateMachine:
    def __init__(self, *, initial_state: str = "NEW") -> None:
        self._state = normalize_state(initial_state)

    @property
    def current_state(self) -> str:
        return self._state

    def can_transition(self, next_state: str) -> bool:
        target = normalize_state(next_state)
        if target == self._state:
            return True
        return target in _ALLOWED_TRANSITIONS[self._state]

    def apply(self, next_state: str) -> OMSStateTransition:
        current = self._state
        target = normalize_state(next_state)

        if target == current:
            return OMSStateTransition(previous_state=current, current_state=current, changed=False)

        if target not in _ALLOWED_TRANSITIONS[current]:
            raise OMSStateTransitionError(
                f"invalid transition: {current} -> {target}; allowed: {sorted(_ALLOWED_TRANSITIONS[current])}"
            )

        self._state = target
        return OMSStateTransition(previous_state=current, current_state=target, changed=True)


def normalize_state(state: str) -> str:
    normalized = state.strip().upper()
    if normalized not in OMS_STATES:
        raise OMSStateTransitionError(f"unknown OMS state: {state}")
    return normalized


def transition_matrix() -> dict[str, tuple[str, ...]]:
    return {state: tuple(sorted(targets)) for state, targets in _ALLOWED_TRANSITIONS.items()}
