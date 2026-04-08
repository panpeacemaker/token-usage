from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class UsageEntry:
    timestamp: datetime
    message_id: str
    request_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_creation_tokens + self.cache_read_tokens


@dataclass
class SessionBlock:
    start: datetime
    end: datetime
    entries: list[UsageEntry] = field(default_factory=list)
    is_gap: bool = False

    @property
    def total_tokens(self) -> int:
        return sum(e.total_tokens for e in self.entries)

    @property
    def models(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.entries:
            out[e.model] = out.get(e.model, 0) + e.total_tokens
        return out

    def contains(self, ts: datetime) -> bool:
        return self.start <= ts < self.end


@dataclass
class ClaudeUsage:
    available: bool
    error: str | None = None
    five_hour_pct: float = 0.0
    five_hour_resets_at: datetime | None = None
    seven_day_pct: float = 0.0
    seven_day_resets_at: datetime | None = None
    seven_day_opus_pct: float | None = None
    seven_day_opus_resets_at: datetime | None = None
    seven_day_sonnet_pct: float | None = None
    seven_day_sonnet_resets_at: datetime | None = None
    subscription_type: str = "unknown"
    rate_limit_tier: str = "unknown"
