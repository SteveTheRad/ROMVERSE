from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from time import time


@dataclass(frozen=True, slots=True)
class AIGovernorPolicy:
    daily_token_budget: int = 50_000
    maximum_request_tokens: int = 4_096
    maximum_concurrency: int = 2
    requests_per_minute: int = 10
    member_requests_per_minute: int = 5

    def validated(self) -> AIGovernorPolicy:
        for value, minimum, maximum, label in (
            (self.daily_token_budget, 1_000, 10_000_000, "daily token budget"),
            (self.maximum_request_tokens, 128, 32_768, "request token limit"),
            (self.maximum_concurrency, 1, 32, "concurrency limit"),
            (self.requests_per_minute, 1, 1_000, "request rate"),
            (self.member_requests_per_minute, 1, 500, "member request rate"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(f"AI Governor {label} is outside the safe boundary")
        if self.member_requests_per_minute > self.requests_per_minute:
            raise ValueError("Member request rate cannot exceed the total request rate")
        return self


@dataclass(frozen=True, slots=True)
class AIGovernorDecision:
    allowed: bool
    reason: str
    lease_id: str = ""
    reserved_tokens: int = 0
    remaining_daily_tokens: int = 0
    retry_after_seconds: int = 0


class AIUsageGovernor:
    """In-process admission control mirrored by a future server-side governor.

    The gateway must stop when this controller denies a request. A cost or fair-use
    limit never converts uncertain AI output into permission to proceed.
    """

    def __init__(
        self,
        policy: AIGovernorPolicy | None = None,
        *,
        clock=time,
    ) -> None:
        self.policy = (policy or AIGovernorPolicy()).validated()
        self.clock = clock
        self._lock = Lock()
        self._day = self._day_key()
        self._used_tokens = 0
        self._active: dict[str, int] = {}
        self._requests: deque[float] = deque()
        self._member_requests: dict[str, deque[float]] = defaultdict(deque)
        self._sequence = 0

    def reserve(self, *, estimated_tokens: int, member_key: str) -> AIGovernorDecision:
        if isinstance(estimated_tokens, bool) or not isinstance(estimated_tokens, int):
            raise ValueError("AI token estimate must be an integer")
        if not 1 <= estimated_tokens <= self.policy.maximum_request_tokens:
            return AIGovernorDecision(
                False,
                "The request exceeds the bounded per-request reasoning budget.",
                remaining_daily_tokens=self.remaining_daily_tokens,
            )
        member = _member_key(member_key)
        with self._lock:
            self._roll_day()
            now = float(self.clock())
            self._trim(self._requests, now)
            member_window = self._member_requests[member]
            self._trim(member_window, now)
            remaining = max(0, self.policy.daily_token_budget - self._used_tokens)
            if len(self._active) >= self.policy.maximum_concurrency:
                return AIGovernorDecision(
                    False,
                    "AI capacity is busy. ROMVERSE stopped rather than weakening verification.",
                    remaining_daily_tokens=remaining,
                    retry_after_seconds=2,
                )
            if len(self._requests) >= self.policy.requests_per_minute:
                return AIGovernorDecision(
                    False,
                    "The shared AI rate limit is active. Existing evidence remains available.",
                    remaining_daily_tokens=remaining,
                    retry_after_seconds=self._retry_after(self._requests, now),
                )
            if len(member_window) >= self.policy.member_requests_per_minute:
                return AIGovernorDecision(
                    False,
                    "Fair-use throttling is active for this member session.",
                    remaining_daily_tokens=remaining,
                    retry_after_seconds=self._retry_after(member_window, now),
                )
            if estimated_tokens > remaining:
                return AIGovernorDecision(
                    False,
                    "The daily AI budget is exhausted. ROMVERSE stopped with uncertainty visible.",
                    remaining_daily_tokens=remaining,
                )
            self._sequence += 1
            lease_id = f"ai-{self._sequence:08d}"
            self._active[lease_id] = estimated_tokens
            self._used_tokens += estimated_tokens
            self._requests.append(now)
            member_window.append(now)
            return AIGovernorDecision(
                True,
                "AI request admitted within the bounded fair-use policy.",
                lease_id,
                estimated_tokens,
                self.policy.daily_token_budget - self._used_tokens,
            )

    def release(self, lease_id: str, *, actual_tokens: int | None = None) -> None:
        with self._lock:
            reserved = self._active.pop(str(lease_id), None)
            if reserved is None:
                raise ValueError("AI Governor lease is unknown or already released")
            if actual_tokens is not None:
                if (
                    isinstance(actual_tokens, bool)
                    or not isinstance(actual_tokens, int)
                    or not 0 <= actual_tokens <= self.policy.maximum_request_tokens
                ):
                    raise ValueError("Actual AI token usage is outside the safe boundary")
                self._used_tokens = max(0, self._used_tokens - reserved + actual_tokens)

    @property
    def active_requests(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def remaining_daily_tokens(self) -> int:
        with self._lock:
            self._roll_day()
            return max(0, self.policy.daily_token_budget - self._used_tokens)

    def _roll_day(self) -> None:
        current = self._day_key()
        if current != self._day and not self._active:
            self._day = current
            self._used_tokens = 0
            self._requests.clear()
            self._member_requests.clear()

    def _day_key(self) -> str:
        return datetime.fromtimestamp(float(self.clock()), UTC).date().isoformat()

    @staticmethod
    def _trim(window: deque[float], now: float) -> None:
        while window and now - window[0] >= 60:
            window.popleft()

    @staticmethod
    def _retry_after(window: deque[float], now: float) -> int:
        return max(1, int(61 - (now - window[0]))) if window else 1


def _member_key(value: object) -> str:
    text = str(value or "anonymous").casefold().strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,127}", text):
        raise ValueError("AI Governor member key must be an anonymized bounded identifier")
    return text
