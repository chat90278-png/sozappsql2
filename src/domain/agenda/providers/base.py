from __future__ import annotations

from typing import Protocol, Sequence

from src.domain.agenda.models import AgendaContext, AgendaItem
from src.domain.agenda.source_models import AgendaCalendarSource


class AgendaProvider(Protocol):
    code: str

    def build(
        self,
        context: AgendaContext,
        sources: Sequence[AgendaCalendarSource],
    ) -> tuple[AgendaItem, ...]:
        ...
