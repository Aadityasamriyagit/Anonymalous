from __future__ import annotations

from datetime import datetime, timezone


class EloService:
    def __init__(self, base: int = 1000) -> None:
        self.base = base

    @staticmethod
    def tier(elo: int) -> str:
        if elo >= 1300:
            return 'elite'
        if elo >= 1100:
            return 'trusted'
        if elo >= 900:
            return 'standard'
        return 'quarantine'

    def update_on_quick_skip(self, current: int, chat_duration_seconds: int) -> int:
        penalty = 20 if chat_duration_seconds < 30 else 5
        return max(100, current - penalty)

    def update_on_long_chat(self, current: int, chat_duration_seconds: int) -> int:
        if chat_duration_seconds >= 600:
            return min(3000, current + 25)
        return current

    def update_on_mutual_reveal(self, current: int) -> int:
        return min(3000, current + 35)

    def update_on_toxicity(self, current: int, toxicity_score: float) -> int:
        deduction = int(15 + toxicity_score * 40)
        return max(100, current - deduction)

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)
