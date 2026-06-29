from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .contract_work_window import ContractWorkWindow

__all__ = ["ContractWorkWindow"]


def __getattr__(name: str):
    if name == "ContractWorkWindow":
        from .contract_work_window import ContractWorkWindow

        return ContractWorkWindow
    raise AttributeError(name)
