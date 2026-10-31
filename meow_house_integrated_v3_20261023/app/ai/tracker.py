"""Time-based zone stabilization that suppresses frame-level jitter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ZoneTransition:
    previous_zone: str | None
    current_zone: str
    changed_at: datetime


class ZoneDebouncer:
    """Switch zones only after a candidate remains stable for a threshold."""

    def __init__(self, threshold_seconds: float = 2.0):
        if threshold_seconds < 0:
            raise ValueError("threshold_seconds must be non-negative")
        self.threshold_seconds = threshold_seconds
        self.current_zone: str | None = None
        self.candidate_zone: str | None = None
        self.candidate_since: datetime | None = None

    def update(self, observed_zone: str | None, observed_at: datetime) -> ZoneTransition | None:
        """Observe one frame and return a transition only when it is confirmed."""
        if observed_zone is None:
            return None
        if observed_zone == self.current_zone:
            self.candidate_zone = None
            self.candidate_since = None
            return None
        if observed_zone != self.candidate_zone:
            self.candidate_zone = observed_zone
            self.candidate_since = observed_at
            if self.threshold_seconds > 0:
                return None
        if self.candidate_since is None:
            self.candidate_since = observed_at
            return None
        if (observed_at - self.candidate_since).total_seconds() < self.threshold_seconds:
            return None
        transition = ZoneTransition(self.current_zone, observed_zone, observed_at)
        self.current_zone = observed_zone
        self.candidate_zone = None
        self.candidate_since = None
        return transition

    def reset(self) -> str | None:
        """Clear confirmed and candidate zones after a sustained loss of detection."""
        previous = self.current_zone
        self.current_zone = None
        self.candidate_zone = None
        self.candidate_since = None
        return previous
