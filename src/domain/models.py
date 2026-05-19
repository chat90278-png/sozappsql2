from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Platform:
    name: str
    sheet_name: str = ""
    active: bool = True


@dataclass
class User:
    name: str
    unit: str = ""
    email: str = ""
    phone: str = ""
    active: bool = True
    note: str = ""


@dataclass
class ComponentDefinition:
    name: str
    version: str = ""
    unit: str = "Adet"
    active: bool = True
    usage: int = 1
    platforms: Dict[str, bool] = field(default_factory=dict)


@dataclass
class ContractSummary:
    platform: str
    contract_no: str
    user: str = ""
    contract_type: str = ""
    status: str = ""
    content: str = ""
    row: Optional[int] = None
    search_text: str = ""


@dataclass
class SystemRecord:
    name: str
    components: Dict[str, float] = field(default_factory=dict)


@dataclass
class DeliveryRecord:
    name: str
    status: str = "PLAN"
    acceptance_date: str = ""
    note: str = ""
    planned: Dict[str, float] = field(default_factory=dict)
    delivered: Dict[str, float] = field(default_factory=dict)
