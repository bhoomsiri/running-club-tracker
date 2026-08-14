from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Time as a dependency. A use case must never call datetime.now() itself —
    injecting this is what makes the tests deterministic."""

    def now(self) -> datetime: ...
