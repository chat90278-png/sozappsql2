from __future__ import annotations

import pytest

from src.domain.agenda.constants import AgendaSeverity
from src.domain.agenda.deadline_stage import (
    DeadlineStage,
    deadline_stage_for_remaining_days,
    deadline_stage_rank,
    deadline_stage_severity,
    deadline_stage_version,
)


@pytest.mark.parametrize(
    ("remaining_days", "expected"),
    [
        (-1, DeadlineStage.OVERDUE),
        (0, DeadlineStage.CRITICAL_1),
        (1, DeadlineStage.CRITICAL_1),
        (2, DeadlineStage.CRITICAL_3),
        (3, DeadlineStage.CRITICAL_3),
        (4, DeadlineStage.CRITICAL_7),
        (7, DeadlineStage.CRITICAL_7),
        (8, DeadlineStage.CRITICAL_15),
        (15, DeadlineStage.CRITICAL_15),
        (16, DeadlineStage.UPCOMING_30),
        (30, DeadlineStage.UPCOMING_30),
        (31, DeadlineStage.UPCOMING_60),
        (60, DeadlineStage.UPCOMING_60),
        (61, DeadlineStage.NONE),
        (None, DeadlineStage.NONE),
    ],
)
def test_deadline_stage_boundaries(remaining_days, expected):
    assert deadline_stage_for_remaining_days(remaining_days) is expected


def test_deadline_stage_severity_mapping_is_stable():
    expected = {
        DeadlineStage.OVERDUE: AgendaSeverity.CRITICAL,
        DeadlineStage.CRITICAL_1: AgendaSeverity.CRITICAL,
        DeadlineStage.CRITICAL_3: AgendaSeverity.CRITICAL,
        DeadlineStage.CRITICAL_7: AgendaSeverity.CRITICAL,
        DeadlineStage.CRITICAL_15: AgendaSeverity.CRITICAL,
        DeadlineStage.UPCOMING_30: AgendaSeverity.ATTENTION,
        DeadlineStage.UPCOMING_60: AgendaSeverity.ATTENTION,
        DeadlineStage.NONE: AgendaSeverity.INFO,
    }

    assert {stage: deadline_stage_severity(stage) for stage in DeadlineStage} == expected


def test_deadline_stage_rank_is_monotonic_by_urgency():
    ordered = [
        DeadlineStage.NONE,
        DeadlineStage.UPCOMING_60,
        DeadlineStage.UPCOMING_30,
        DeadlineStage.CRITICAL_15,
        DeadlineStage.CRITICAL_7,
        DeadlineStage.CRITICAL_3,
        DeadlineStage.CRITICAL_1,
        DeadlineStage.OVERDUE,
    ]

    assert [deadline_stage_rank(stage) for stage in ordered] == [0, 10, 20, 30, 40, 50, 60, 70]


def test_deadline_stage_version_is_stable_stage_code():
    for stage in DeadlineStage:
        assert deadline_stage_version(stage) == stage.value
        assert deadline_stage_version(stage.value) == stage.value


@pytest.mark.parametrize(
    "helper",
    [deadline_stage_severity, deadline_stage_rank, deadline_stage_version],
)
def test_deadline_stage_helpers_reject_invalid_stage_string(helper):
    with pytest.raises(ValueError):
        helper("NOT_A_STAGE")
