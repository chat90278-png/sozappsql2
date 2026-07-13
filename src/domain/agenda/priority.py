from __future__ import annotations

from src.domain.agenda.constants import AgendaSeverity


AGENDA_SEVERITY_RANK: dict[AgendaSeverity, int] = {
    AgendaSeverity.INFO: 0,
    AgendaSeverity.ATTENTION: 1,
    AgendaSeverity.CRITICAL: 2,
}


def severity_rank(severity: AgendaSeverity | str) -> int:
    parsed = severity if isinstance(severity, AgendaSeverity) else AgendaSeverity(str(severity).strip())
    return AGENDA_SEVERITY_RANK[parsed]
