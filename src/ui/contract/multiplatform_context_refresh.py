from __future__ import annotations

from functools import wraps

from src.ui.contract.contract_work_window import ContractWorkWindow

_PATCH_FLAG = "_multiplatform_context_refresh_patch_installed"
_ORIGINAL_SET_ACTIVE_PLATFORM = "_multiplatform_original_set_active_platform"
_ORIGINAL_REFRESH_SD_SIDEBAR = "_multiplatform_original_refresh_sd_sidebar"
_SWITCH_FLAG = "_switching_active_platform_context"


def install_multiplatform_context_refresh_fix() -> None:
    """Keep platform switches from feeding the old detail table into new data.

    ``ContractWorkWindow.set_active_platform`` caches the outgoing platform first,
    then replaces ``systems``/``deliveries`` and calls ``refresh``.  ``refresh``
    starts with ``refresh_sd_sidebar``; that method normally caches the current
    context again.  During a platform switch the summary table still contains the
    outgoing platform at that exact moment, so the second cache calls
    ``sync_summary_to_system`` and can write those stale rows into the newly loaded
    platform before ``refresh_right`` repaints the table.

    The outgoing cache must still run.  Only the nested sidebar cache that happens
    while the active-platform context is being repainted is suppressed.  Normal
    sidebar refreshes keep their existing cache behaviour.
    """
    if getattr(ContractWorkWindow, _PATCH_FLAG, False):
        return

    original_set_active_platform = ContractWorkWindow.set_active_platform
    original_refresh_sd_sidebar = ContractWorkWindow.refresh_sd_sidebar
    setattr(
        ContractWorkWindow,
        _ORIGINAL_SET_ACTIVE_PLATFORM,
        original_set_active_platform,
    )
    setattr(
        ContractWorkWindow,
        _ORIGINAL_REFRESH_SD_SIDEBAR,
        original_refresh_sd_sidebar,
    )

    @wraps(original_refresh_sd_sidebar)
    def refresh_sd_sidebar_without_stale_platform_cache(self, *args, **kwargs):
        if not bool(getattr(self, _SWITCH_FLAG, False)):
            return original_refresh_sd_sidebar(self, *args, **kwargs)

        previous_refreshing = bool(
            getattr(self, "_refreshing_contract_context", False)
        )
        self._refreshing_contract_context = True
        try:
            return original_refresh_sd_sidebar(self, *args, **kwargs)
        finally:
            self._refreshing_contract_context = previous_refreshing

    @wraps(original_set_active_platform)
    def set_active_platform_consistently(self, platform_id: int):
        previous_switching = bool(getattr(self, _SWITCH_FLAG, False))
        setattr(self, _SWITCH_FLAG, True)
        try:
            return original_set_active_platform(self, platform_id)
        finally:
            setattr(self, _SWITCH_FLAG, previous_switching)

    ContractWorkWindow.refresh_sd_sidebar = refresh_sd_sidebar_without_stale_platform_cache
    ContractWorkWindow.set_active_platform = set_active_platform_consistently
    setattr(ContractWorkWindow, _PATCH_FLAG, True)
