"""Turning tabular data into a spreadsheet file.

A port, so the use case can assemble the club's records without knowing that xlsx —
or openpyxl — exists. What crosses this boundary is a list of sheets made of ordinary
values; the adapter decides what a file looks like.

`Decimal` is in `Cell` and `float` deliberately is not. Points, distance and pace are
the numbers this export exists to hand someone, and golden rule #6 does not stop being
true because the destination is a spreadsheet: a balance that arrives as
10.199999999999999 is a wrong answer in a file people will treat as authoritative.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

Cell = str | int | Decimal | date | datetime | bool | None


@dataclass(frozen=True)
class Sheet:
    """One tab. `key` is the ASCII name the audit row records; `title` is what a human
    reads on the tab, in Thai."""

    key: str
    title: str
    headers: Sequence[str]
    rows: Sequence[Sequence[Cell]]

    @property
    def row_count(self) -> int:
        return len(self.rows)


class WorkbookRenderer(Protocol):
    def render(self, sheets: Sequence[Sheet]) -> bytes:
        """The whole workbook as bytes. One file, one tab per sheet, in order."""
        ...
