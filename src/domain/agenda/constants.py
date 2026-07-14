from __future__ import annotations

from enum import Enum


class AgendaLifecycleType(str, Enum):
    CONDITION = "CONDITION"
    EVENT = "EVENT"


class AgendaSeverity(str, Enum):
    INFO = "INFO"
    ATTENTION = "ATTENTION"
    CRITICAL = "CRITICAL"


class AgendaPresentationProfileCode(str, Enum):
    PERSONAL = "PERSONAL"
    MANAGEMENT = "MANAGEMENT"
    SYSTEM = "SYSTEM"
    VIEW_ONLY = "VIEW_ONLY"


class AgendaContractScopeCode(str, Enum):
    RESPONSIBLE = "RESPONSIBLE"
    ALL_VISIBLE = "ALL_VISIBLE"
