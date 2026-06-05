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
    component_notes: Dict[str, str] = field(default_factory=dict)


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
    id: int = 0
