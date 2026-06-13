# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ComponentDef:
    name: str
    version: str = ""
    unit: str = "Adet"
    active: bool = True
    usage: int = 1
    platforms: Dict[str, bool] = field(default_factory=dict)


@dataclass
class ContractInfo:
    no: str
    platform: str
    user: str
    yi_yd: str
    contract_type: str
    signature_date: str
    t0_date: str
    t0_months: int
    completion_date: str
    status: str = "PLAN"
    note: str = ""
    acceptance_date: str = ""
    entry_start_row: int = 0
    sd_anchor_start_row: int = 0
    sd_anchor_end_row: int = 0
    sd_anchor_platform: str = ""
    sd_anchor_no: str = ""
    users: list[str] = field(default_factory=list)
    id: int = 0
    contract_id: int = 0
    platform_id: int = 0
    primary_platform_id: int = 0
    primary_platform: str = ""
    platforms: list[dict] = field(default_factory=list)
    platform_names: list[str] = field(default_factory=list)
    platform_ids: list[int] = field(default_factory=list)


@dataclass
class SystemInfo:
    name: str
    components: Dict[str, float]
    component_notes: Dict[str, str] = field(default_factory=dict)
    t0_date: str = ""
    t0_months: int = 0
    completion_date: str = ""
    status: str = "Başlanmadı"
    acceptance_date: str = ""
    platform_id: int = 0

    def __post_init__(self) -> None:
        # Preserve the legacy positional constructor contract from before
        # component_notes was inserted as a dataclass field.
        if not isinstance(self.component_notes, dict):
            t0_date = self.component_notes
            t0_months = self.t0_date
            completion_date = self.t0_months
            status = self.completion_date
            acceptance_date = self.status
            self.component_notes = {}
            self.t0_date = str(t0_date or "")
            self.t0_months = int(t0_months or 0)
            self.completion_date = str(completion_date or "")
            self.status = str(status or "Başlanmadı")
            self.acceptance_date = str(acceptance_date or "")


@dataclass
class DeliveryInfo:
    name: str
    status: str
    acceptance_date: str
    note: str
    planned: Dict[str, float]
    delivered: Dict[str, float]
    t0_date: str = ""
    t0_months: int = 0
    completion_date: str = ""
    delivery_user: str = ""


@dataclass
class TagDef:
    name: str
    color: str = "#3B82F6"
    note: str = ""
    active: bool = True
