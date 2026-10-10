"""Singapore's monsoon seasons (Meteorological Service Singapore).

Northeast Monsoon from December to early March, first inter-monsoon from late
March to May, Southwest Monsoon from June to September, second inter-monsoon in
October and November. The boundary in March is set to the 16th.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum


class Season(StrEnum):
    """Monsoon season labels."""

    NE_MONSOON = "ne_monsoon"
    INTER_MONSOON_1 = "inter_monsoon_1"
    SW_MONSOON = "sw_monsoon"
    INTER_MONSOON_2 = "inter_monsoon_2"


SEASON_LABELS = {
    Season.NE_MONSOON: "Northeast Monsoon (Dec to early Mar)",
    Season.INTER_MONSOON_1: "Inter-monsoon (late Mar to May)",
    Season.SW_MONSOON: "Southwest Monsoon (Jun to Sep)",
    Season.INTER_MONSOON_2: "Inter-monsoon (Oct to Nov)",
}


def season_of(day: date | datetime) -> Season:
    """Monsoon season of a calendar day in Singapore."""
    m, d = day.month, day.day
    if m in (12, 1, 2) or (m == 3 and d < 16):
        return Season.NE_MONSOON
    if m in (3, 4, 5):
        return Season.INTER_MONSOON_1
    if m in (6, 7, 8, 9):
        return Season.SW_MONSOON
    return Season.INTER_MONSOON_2


def decimal_year(moment: datetime) -> float:
    """Year with the elapsed fraction of that year, e.g. 2018.39 for late May 2018."""
    start = datetime(moment.year, 1, 1, tzinfo=moment.tzinfo)
    end = datetime(moment.year + 1, 1, 1, tzinfo=moment.tzinfo)
    return moment.year + (moment - start).total_seconds() / (end - start).total_seconds()
