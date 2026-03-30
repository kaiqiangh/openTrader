from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class QuotaLimits:
    daily_token_limit: int | None
    monthly_cost_limit: float | None
    is_hard_limit: bool = True


@dataclass(frozen=True, slots=True)
class QuotaUsage:
    daily_tokens: int
    monthly_cost: float


class LLMQuotaStore(Protocol):
    async def get_limits(self, *, strategy_id: str, agent_name: str) -> QuotaLimits: ...

    async def get_usage(self, *, strategy_id: str, agent_name: str) -> QuotaUsage: ...

    async def increment_usage(
        self,
        *,
        strategy_id: str,
        agent_name: str,
        added_tokens: int,
        added_cost: float,
    ) -> QuotaUsage: ...
