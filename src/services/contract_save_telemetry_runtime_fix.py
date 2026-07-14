from __future__ import annotations

import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable

from src.services import perf_tracker


_MAIN_PATCH_FLAG = "_contract_save_telemetry_main_patch_installed"
_WORK_PATCH_FLAG = "_contract_save_telemetry_work_patch_installed"


def _store_path(store: Any):
    return getattr(store, "path", None)


def _record_save(
    store: Any,
    duration_ms: float,
    *,
    success: bool,
    source: str,
    save_mode: str,
    platform: str = "",
    contract_no: str = "",
    error: str = "",
    extra: dict | None = None,
) -> None:
    path = _store_path(store)
    if not path:
        return
    metadata = {
        "source": str(source or "Sözleşme ekranı"),
        "save_mode": str(save_mode or "direct"),
        "platform": str(platform or ""),
        "contract_no": str(contract_no or ""),
    }
    if error:
        metadata["error"] = str(error)
    metadata.update(dict(extra or {}))
    try:
        perf_tracker.record(
            perf_tracker.OP_CONTRACT_SAVE,
            path,
            duration_ms,
            success=success,
            meta=metadata,
        )
    except Exception:
        # Telemetry must never break the save flow.
        pass


def _replace_instance_callable(instance: Any, name: str, replacement: Callable):
    namespace = getattr(instance, "__dict__", None)
    had_instance_value = isinstance(namespace, dict) and name in namespace
    previous_instance_value = namespace.get(name) if had_instance_value else None
    setattr(instance, name, replacement)
    return had_instance_value, previous_instance_value


def _restore_instance_callable(
    instance: Any,
    name: str,
    had_instance_value: bool,
    previous_instance_value: Any,
) -> None:
    try:
        if had_instance_value:
            setattr(instance, name, previous_instance_value)
        else:
            delattr(instance, name)
    except Exception:
        pass


def _patch_main_window_class(main_window_class) -> None:
    if getattr(main_window_class, _MAIN_PATCH_FLAG, False):
        return

    original_new_contract = main_window_class.new_contract

    @wraps(original_new_contract)
    def new_contract_with_save_measurement(self, *args, **kwargs):
        store = getattr(self, "store", None)
        original_write = getattr(store, "write_contract", None)
        if store is None or not callable(original_write) or not _store_path(store):
            return original_new_contract(self, *args, **kwargs)

        @wraps(original_write)
        def measured_write_contract(*write_args, **write_kwargs):
            ci = write_args[0] if write_args else write_kwargs.get("ci")
            platform = str(getattr(ci, "platform", "") or "")
            contract_no = str(getattr(ci, "no", "") or "")
            started = time.perf_counter()
            success = False
            error = ""
            try:
                result = original_write(*write_args, **write_kwargs)
                success = True
                return result
            except Exception as exc:
                error = str(exc)
                raise
            finally:
                _record_save(
                    store,
                    (time.perf_counter() - started) * 1000.0,
                    success=success,
                    source="Yeni sözleşme ekranı",
                    save_mode="create",
                    platform=platform,
                    contract_no=contract_no,
                    error=error,
                )

        try:
            had_value, previous_value = _replace_instance_callable(
                store,
                "write_contract",
                measured_write_contract,
            )
        except Exception:
            return original_new_contract(self, *args, **kwargs)

        try:
            return original_new_contract(self, *args, **kwargs)
        finally:
            _restore_instance_callable(
                store,
                "write_contract",
                had_value,
                previous_value,
            )

    main_window_class.new_contract = new_contract_with_save_measurement
    setattr(main_window_class, _MAIN_PATCH_FLAG, True)


def _patch_contract_work_window_class(contract_work_window_class) -> None:
    if getattr(contract_work_window_class, _WORK_PATCH_FLAG, False):
        return

    original_save_family = contract_work_window_class._save_context_family

    @wraps(original_save_family)
    def save_family_with_measurement(self, *args, **kwargs):
        store = getattr(self, "store", None)
        original_batch_save = getattr(store, "batch_save", None)
        if store is None or not callable(original_batch_save) or not _store_path(store):
            return original_save_family(self, *args, **kwargs)

        depth = 0

        @contextmanager
        def measured_batch_save():
            nonlocal depth
            outermost = depth == 0
            depth += 1
            started = time.perf_counter() if outermost else 0.0
            success = False
            error = ""
            try:
                with original_batch_save():
                    yield
                success = True
            except Exception as exc:
                error = str(exc)
                raise
            finally:
                depth -= 1
                if outermost:
                    ci = getattr(self, "ci", None)
                    context_cache = getattr(self, "_context_cache", {}) or {}
                    _record_save(
                        store,
                        (time.perf_counter() - started) * 1000.0,
                        success=success,
                        source="Sözleşme detay ekranı",
                        save_mode="family",
                        platform=str(getattr(ci, "platform", "") or ""),
                        contract_no=str(getattr(ci, "no", "") or ""),
                        error=error,
                        extra={"context_count": len(context_cache)},
                    )

        try:
            had_value, previous_value = _replace_instance_callable(
                store,
                "batch_save",
                measured_batch_save,
            )
        except Exception:
            return original_save_family(self, *args, **kwargs)

        try:
            return original_save_family(self, *args, **kwargs)
        finally:
            _restore_instance_callable(
                store,
                "batch_save",
                had_value,
                previous_value,
            )

    contract_work_window_class._save_context_family = save_family_with_measurement
    setattr(contract_work_window_class, _WORK_PATCH_FLAG, True)


def install_contract_save_telemetry_fix() -> None:
    """Install telemetry around save paths that bypass ContractSaveWorker."""
    from src.ui.main_window import MainWindow
    from src.ui.contract.contract_work_window import ContractWorkWindow

    _patch_main_window_class(MainWindow)
    _patch_contract_work_window_class(ContractWorkWindow)
