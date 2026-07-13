from __future__ import annotations

from enum import Enum

from src.domain.agenda.constants import AgendaSeverity


class DeadlineStage(str, Enum):
    OVERDUE = "OVERDUE"
    CRITICAL_1 = "CRITICAL_1"
    CRITICAL_3 = "CRITICAL_3"
    CRITICAL_7 = "CRITICAL_7"
    CRITICAL_15 = "CRITICAL_15"
    UPCOMING_30 = "UPCOMING_30"
    UPCOMING_60 = "UPCOMING_60"
    NONE = "NONE"


_DEADLINE_STAGE_SEVERITY: dict[DeadlineStage, AgendaSeverity] = {
    DeadlineStage.OVERDUE: AgendaSeverity.CRITICAL,
    DeadlineStage.CRITICAL_1: AgendaSeverity.CRITICAL,
    DeadlineStage.CRITICAL_3: AgendaSeverity.CRITICAL,
    DeadlineStage.CRITICAL_7: AgendaSeverity.CRITICAL,
    DeadlineStage.CRITICAL_15: AgendaSeverity.CRITICAL,
    DeadlineStage.UPCOMING_30: AgendaSeverity.ATTENTION,
    DeadlineStage.UPCOMING_60: AgendaSeverity.ATTENTION,
    DeadlineStage.NONE: AgendaSeverity.INFO,
}

_DEADLINE_STAGE_RANK: dict[DeadlineStage, int] = {
    DeadlineStage.NONE: 0,
    DeadlineStage.UPCOMING_60: 10,
    DeadlineStage.UPCOMING_30: 20,
    DeadlineStage.CRITICAL_15: 30,
    DeadlineStage.CRITICAL_7: 40,
    DeadlineStage.CRITICAL_3: 50,
    DeadlineStage.CRITICAL_1: 60,
    DeadlineStage.OVERDUE: 70,
}


def _parse_deadline_stage(stage: DeadlineStage | str) -> DeadlineStage:
    return stage if isinstance(stage, DeadlineStage) else DeadlineStage(str(stage).strip())


def deadline_stage_for_remaining_days(remaining_days: int | None) -> DeadlineStage:
    if remaining_days is None:
        return DeadlineStage.NONE
    if remaining_days < 0:
        return DeadlineStage.OVERDUE
    if remaining_days <= 1:
        return DeadlineStage.CRITICAL_1
    if remaining_days <= 3:
        return DeadlineStage.CRITICAL_3
    if remaining_days <= 7:
        return DeadlineStage.CRITICAL_7
    if remaining_days <= 15:
        return DeadlineStage.CRITICAL_15
    if remaining_days <= 30:
        return DeadlineStage.UPCOMING_30
    if remaining_days <= 60:
        return DeadlineStage.UPCOMING_60
    return DeadlineStage.NONE


def deadline_stage_severity(stage: DeadlineStage | str) -> AgendaSeverity:
    return _DEADLINE_STAGE_SEVERITY[_parse_deadline_stage(stage)]


def deadline_stage_rank(stage: DeadlineStage | str) -> int:
    return _DEADLINE_STAGE_RANK[_parse_deadline_stage(stage)]


def deadline_stage_version(stage: DeadlineStage | str) -> str:
    return _parse_deadline_stage(stage).value
