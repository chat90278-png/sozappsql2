from __future__ import annotations

from typing import Protocol

from src.domain.agenda.models import AgendaContext, AgendaItem
from src.domain.agenda.source_models import AgendaSourceBundle


class AgendaProvider(Protocol):
    code: str

    def is_enabled(self, context: AgendaContext) -> bool:
        ...

    def build(
        self,
        context: AgendaContext,
        sources: AgendaSourceBundle,
    ) -> tuple[AgendaItem, ...]:
        ...
