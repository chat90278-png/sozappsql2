from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .analysis_dashboard_layout import (
    CompactMode,
    DashboardCardPlacement,
    DashboardLayoutEngine,
    DashboardLayoutSettings,
    LayoutValidationError,
    first_available_position,
    pack_placements,
    placement_order,
)
from .analysis_models import AnalysisCard, CardLayoutHints, CardSize, DashboardItem


WORKSPACE_SCHEMA_VERSION = 2
WORKSPACE_FORMAT_VERSION = WORKSPACE_SCHEMA_VERSION
CUSTOM_DASHBOARD_ID = "custom_dashboard"
LEGACY_SIZE_WIDTHS = {
    "small": 3,
    "medium": 6,
    "large": 9,
    "wide": 12,
    "full": 12,
}
_STS_VERSIONED_STEM_RE = re.compile(
    r"^(?P<code>STS-[A-Z]\d+)__v\d+__\d{4}-\d{2}-\d{2}_\d{2}-\d{2}$",
    re.IGNORECASE,
)


class DashboardWorkspaceError(RuntimeError):
    pass


class DashboardWorkspaceCorruptError(DashboardWorkspaceError):
    pass


class DashboardWorkspaceMigrationError(DashboardWorkspaceError):
    pass


def _source_path(source: Any) -> Path | None:
    if isinstance(source, (str, Path)):
        try:
            return Path(source).expanduser()
        except Exception:
            return None
    for attr in ("path", "db_path", "database_path"):
        value = getattr(source, attr, None)
        if value:
            try:
                return Path(value).expanduser()
            except Exception:
                return None
    store = getattr(source, "store", None)
    value = getattr(store, "path", None) if store is not None else None
    if value:
        try:
            return Path(value).expanduser()
        except Exception:
            return None
    return None


def source_workspace_key(source: Any) -> str:
    """Return a stable local key without reading or modifying the STS file."""

    path = _source_path(source)
    if path is None:
        return "sample"
    try:
        resolved = path.resolve(strict=False)
    except Exception:
        resolved = path.absolute()

    match = _STS_VERSIONED_STEM_RE.match(path.stem)
    if match:
        normalized = f"{resolved.parent}|{str(match.group('code')).upper()}"
    else:
        normalized = str(resolved)
    if os.name == "nt":
        normalized = normalized.casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def default_workspace_root() -> Path:
    local_app_data = str(os.getenv("LOCALAPPDATA") or "").strip()
    if local_app_data:
        return Path(local_app_data) / "STS" / "analysis_center" / "dashboards"
    return Path.home() / ".sts" / "analysis_center" / "dashboards"


def _card_key(source_screen_id: str, card_id: str) -> str:
    return f"{source_screen_id}:{card_id}"


def _card_hints_index(dashboard_items: Iterable[DashboardItem] | None) -> dict[str, CardLayoutHints]:
    hints: dict[str, CardLayoutHints] = {}
    for item in dashboard_items or ():
        for card in item.cards:
            hints[_card_key(item.item_id, card.card_id)] = card.resolved_layout_hints()
    return hints


def _legacy_card_size(width: int) -> CardSize:
    if width <= 3:
        return CardSize.SMALL
    if width <= 6:
        return CardSize.MEDIUM
    if width <= 9:
        return CardSize.LARGE
    return CardSize.WIDE


def _bounded_default_width(hints: CardLayoutHints, columns: int) -> int:
    width = max(hints.min_w, min(hints.default_w, columns))
    if hints.max_w is not None:
        width = min(width, hints.max_w)
    return width


def _bounded_legacy_width(size: str, hints: CardLayoutHints, columns: int) -> int:
    width = LEGACY_SIZE_WIDTHS.get(size, LEGACY_SIZE_WIDTHS[CardSize.MEDIUM.value])
    width = max(width, hints.min_w)
    if hints.max_w is not None:
        width = min(width, hints.max_w)
    return min(width, columns)


@dataclass(slots=True)
class DashboardWorkspace:
    source_key: str
    placements: list[DashboardCardPlacement] = field(default_factory=list)
    workspace_id: str = "default"
    layout: DashboardLayoutSettings = field(default_factory=DashboardLayoutSettings)
    schema_version: int = WORKSPACE_SCHEMA_VERSION
    _layout_hints: dict[str, CardLayoutHints] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.source_key = str(self.source_key or "sample")
        self.workspace_id = str(self.workspace_id or "default")
        if self.schema_version != WORKSPACE_SCHEMA_VERSION:
            raise LayoutValidationError(
                f"Desteklenmeyen workspace schema_version: {self.schema_version}"
            )
        self.placements = sorted(self.placements, key=placement_order)

    @property
    def engine(self) -> DashboardLayoutEngine:
        return DashboardLayoutEngine(self.layout)

    def working_copy(self) -> "DashboardWorkspace":
        return deepcopy(self)

    def validate(self) -> None:
        self.engine.validate(self.placements, self._layout_hints)

    @property
    def layout_hints_by_placement(self) -> dict[str, CardLayoutHints]:
        return dict(self._layout_hints)

    def layout_hints_for(self, placement_id: str) -> CardLayoutHints:
        return self._layout_hints.get(placement_id, CardLayoutHints())

    def bind_layout_hints(self, placement_id: str, hints: CardLayoutHints) -> None:
        """Bind current card constraints, reflowing with the existing engine if needed."""

        placement = next(
            (item for item in self.placements if item.placement_id == placement_id),
            None,
        )
        if placement is None:
            return
        candidate_hints = dict(self._layout_hints)
        candidate_hints[placement_id] = hints
        try:
            self.engine.validate(self.placements, candidate_hints)
        except LayoutValidationError:
            remaining_hints = dict(candidate_hints)
            remaining_hints.pop(placement_id, None)
            remaining = self.engine.remove(
                self.placements,
                placement_id=placement_id,
                hints_by_placement=remaining_hints,
            )
            candidate = deepcopy(placement)
            candidate.w = max(hints.min_w, candidate.w)
            candidate.h = max(hints.min_h, candidate.h)
            if hints.max_w is not None:
                candidate.w = min(candidate.w, hints.max_w)
            if hints.max_h is not None:
                candidate.h = min(candidate.h, hints.max_h)
            candidate.w = min(candidate.w, self.layout.columns)
            self.placements = self.engine.add(
                remaining,
                candidate,
                hints_by_placement=candidate_hints,
            )
        self._layout_hints = candidate_hints

    def apply_placements(self, placements: Iterable[DashboardCardPlacement]) -> None:
        candidate = sorted(deepcopy(list(placements)), key=placement_order)
        self.engine.validate(candidate, self._layout_hints)
        self.placements = candidate

    def reset_layout(self) -> None:
        defaults: list[DashboardCardPlacement] = []
        for source in sorted(self.placements, key=placement_order):
            placement = deepcopy(source)
            hints = self.layout_hints_for(placement.placement_id)
            placement.w = _bounded_default_width(hints, self.layout.columns)
            placement.h = hints.default_h
            placement.x = 0
            placement.y = 0
            defaults.append(placement)
        self.apply_placements(pack_placements(defaults, columns=self.layout.columns))

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "workspace_id": self.workspace_id,
            "source_key": self.source_key,
            "layout": self.layout.to_dict(),
            "placements": [placement.to_dict() for placement in sorted(self.placements, key=placement_order)],
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        source_key: str,
        card_hints: Mapping[str, CardLayoutHints] | None = None,
    ) -> "DashboardWorkspace":
        try:
            schema_version = int(payload.get("schema_version"))
        except (TypeError, ValueError) as exc:
            raise LayoutValidationError("Workspace schema_version geçersiz.") from exc
        if schema_version != WORKSPACE_SCHEMA_VERSION:
            raise LayoutValidationError(f"Desteklenmeyen workspace schema_version: {schema_version}")

        raw_placements = payload.get("placements") or []
        if not isinstance(raw_placements, list):
            raise LayoutValidationError("Workspace placements list olmalıdır.")
        if any(not isinstance(raw, Mapping) for raw in raw_placements):
            raise LayoutValidationError("Workspace placement kayıtları object olmalıdır.")
        raw_layout = payload.get("layout")
        if raw_layout is not None and not isinstance(raw_layout, Mapping):
            raise LayoutValidationError("Workspace layout object olmalıdır.")
        placements = [DashboardCardPlacement.from_dict(raw) for raw in raw_placements]
        workspace = cls(
            source_key=source_key,
            placements=placements,
            workspace_id=str(payload.get("workspace_id") or "default"),
            layout=DashboardLayoutSettings.from_dict(raw_layout),
            schema_version=schema_version,
        )
        source_hints = card_hints or {}
        workspace._layout_hints = {
            placement.placement_id: source_hints[_card_key(placement.source_screen_id, placement.card_id)]
            for placement in workspace.placements
            if _card_key(placement.source_screen_id, placement.card_id) in source_hints
        }
        workspace.validate()
        return workspace

    @staticmethod
    def card_key(card: AnalysisCard) -> str:
        return _card_key(str(card.screen_id or ""), str(card.card_id or ""))

    def contains(self, source_screen_id: str, card_id: str) -> bool:
        key = _card_key(source_screen_id, card_id)
        return any(
            _card_key(placement.source_screen_id, placement.card_id) == key
            for placement in self.placements
        )

    def placement_for_source(self, source_screen_id: str, card_id: str) -> DashboardCardPlacement | None:
        key = _card_key(source_screen_id, card_id)
        matches = [
            placement
            for placement in self.placements
            if _card_key(placement.source_screen_id, placement.card_id) == key
        ]
        return min(matches, key=placement_order) if matches else None

    def pin(self, card: AnalysisCard) -> bool:
        source_screen_id = str(card.screen_id or "").strip()
        card_id = str(card.card_id or "").strip()
        if not source_screen_id or not card_id or source_screen_id == CUSTOM_DASHBOARD_ID:
            return False
        if self.contains(source_screen_id, card_id):
            return False

        hints = card.resolved_layout_hints()
        placement_id = self._next_placement_id()
        width = _bounded_default_width(hints, self.layout.columns)
        x, y = first_available_position(
            self.placements,
            w=width,
            h=hints.default_h,
            columns=self.layout.columns,
        )
        placement = DashboardCardPlacement(
            placement_id=placement_id,
            source_screen_id=source_screen_id,
            card_id=card_id,
            x=x,
            y=y,
            w=width,
            h=hints.default_h,
        )
        hints_by_placement = dict(self._layout_hints)
        hints_by_placement[placement_id] = hints
        self.placements = self.engine.add(
            self.placements,
            placement,
            hints_by_placement=hints_by_placement,
        )
        self._layout_hints = hints_by_placement
        return True

    def add_placement(
        self,
        placement: DashboardCardPlacement,
        *,
        layout_hints: CardLayoutHints | None = None,
    ) -> None:
        hints = dict(self._layout_hints)
        if layout_hints is not None:
            hints[placement.placement_id] = layout_hints
        self.placements = self.engine.add(
            self.placements,
            placement,
            hints_by_placement=hints,
        )
        self._layout_hints = hints

    def remove(self, source_screen_id: str, card_id: str) -> bool:
        placement = self.placement_for_source(source_screen_id, card_id)
        if placement is None:
            return False
        self.remove_placement(placement.placement_id)
        return True

    def remove_placement(self, placement_id: str) -> None:
        hints = dict(self._layout_hints)
        hints.pop(placement_id, None)
        self.placements = self.engine.remove(
            self.placements,
            placement_id=placement_id,
            hints_by_placement=hints,
        )
        self._layout_hints = hints

    def move_placement(self, placement_id: str, *, x: int, y: int) -> None:
        self.placements = self.engine.move(
            self.placements,
            placement_id=placement_id,
            x=x,
            y=y,
            hints_by_placement=self._layout_hints,
        )

    def resize_placement(self, placement_id: str, *, w: int, h: int) -> None:
        self.placements = self.engine.resize(
            self.placements,
            placement_id=placement_id,
            w=w,
            h=h,
            hints_by_placement=self._layout_hints,
        )

    def compact(self) -> None:
        self.placements = self.engine.compact(
            self.placements,
            hints_by_placement=self._layout_hints,
        )

    def move(self, source_screen_id: str, card_id: str, delta: int) -> bool:
        ordered = sorted(self.placements, key=placement_order)
        placement = self.placement_for_source(source_screen_id, card_id)
        if placement is None:
            return False
        index = next(
            idx for idx, item in enumerate(ordered) if item.placement_id == placement.placement_id
        )
        target = max(0, min(len(ordered) - 1, index + int(delta)))
        if target == index:
            return False
        ordered.insert(target, ordered.pop(index))
        self.placements = pack_placements(ordered, columns=self.layout.columns)
        self.validate()
        return True

    def set_size(self, source_screen_id: str, card_id: str, size: CardSize) -> bool:
        placement = self.placement_for_source(source_screen_id, card_id)
        if placement is None:
            return False
        hints = self._layout_hints.get(placement.placement_id, CardLayoutHints())
        target_w = _bounded_legacy_width(size.value, hints, self.layout.columns)
        if placement.w == target_w:
            return False
        self.resize_placement(placement.placement_id, w=target_w, h=placement.h)
        return True

    def prune_orphaned_placements(
        self,
        dashboard_items: Iterable[DashboardItem],
        *,
        additional_card_keys: Iterable[str] = (),
        protected_source_ids: Iterable[str] = (),
    ) -> list[str]:
        """Remove placements whose source card no longer exists, preserving all other geometry."""

        known_keys = {
            _card_key(item.item_id, card.card_id)
            for item in dashboard_items
            for card in item.cards
            if card.enabled
        }
        known_keys.update(str(key) for key in additional_card_keys if str(key).strip())
        protected_sources = {
            str(source_id).strip()
            for source_id in protected_source_ids
            if str(source_id).strip()
        }
        if not known_keys and not protected_sources:
            return []
        orphaned = [
            placement
            for placement in self.placements
            if placement.source_screen_id not in protected_sources
            and _card_key(placement.source_screen_id, placement.card_id) not in known_keys
        ]
        if not orphaned:
            return []
        orphan_ids = {placement.placement_id for placement in orphaned}
        kept = [placement for placement in self.placements if placement.placement_id not in orphan_ids]
        hints = {
            placement_id: hint
            for placement_id, hint in self._layout_hints.items()
            if placement_id not in orphan_ids
        }
        self.engine.validate(kept, hints)
        self.placements = sorted(deepcopy(kept), key=placement_order)
        self._layout_hints = hints
        return [
            _card_key(placement.source_screen_id, placement.card_id)
            for placement in sorted(orphaned, key=placement_order)
        ]

    def resolve_cards(
        self,
        dashboard_items: Iterable[DashboardItem],
        *,
        additional_cards: Iterable[AnalysisCard] = (),
    ) -> tuple[list[AnalysisCard], list[str]]:
        card_index: dict[str, AnalysisCard] = {}
        for item in dashboard_items:
            for card in item.cards:
                if card.enabled:
                    card_index[_card_key(item.item_id, card.card_id)] = card
        for card in additional_cards:
            source_screen_id = str(card.screen_id or "").strip()
            card_id = str(card.card_id or "").strip()
            if card.enabled and source_screen_id and card_id:
                card_index[_card_key(source_screen_id, card_id)] = card

        cards: list[AnalysisCard] = []
        missing: list[str] = []
        resolved_hints = dict(self._layout_hints)
        for placement in list(sorted(self.placements, key=placement_order)):
            source_key = _card_key(placement.source_screen_id, placement.card_id)
            source = card_index.get(source_key)
            if source is None:
                continue
            hints = source.resolved_layout_hints()
            self.bind_layout_hints(placement.placement_id, hints)
            resolved_hints[placement.placement_id] = hints
        for placement in sorted(self.placements, key=placement_order):
            source_key = _card_key(placement.source_screen_id, placement.card_id)
            source = card_index.get(source_key)
            if source is None:
                missing.append(source_key)
                continue
            hints = source.resolved_layout_hints()
            resolved_hints[placement.placement_id] = hints
            card = deepcopy(source)
            card.screen_id = CUSTOM_DASHBOARD_ID
            card.size = _legacy_card_size(placement.w)
            card.layout_hints = hints
            card.sort_order = placement.y * self.layout.columns + placement.x
            card.meta = dict(card.meta)
            card.meta.update({
                "dashboard_source_screen_id": placement.source_screen_id,
                "dashboard_source_card_id": placement.card_id,
                "dashboard_placement_id": placement.placement_id,
                "dashboard_x": placement.x,
                "dashboard_y": placement.y,
                "dashboard_w": placement.w,
                "dashboard_h": placement.h,
                "dashboard_locked": placement.locked,
            })
            cards.append(card)
        self._layout_hints = resolved_hints
        self.validate()
        return cards, missing

    def _next_placement_id(self) -> str:
        existing = {placement.placement_id for placement in self.placements}
        index = 1
        while f"placement-{index}" in existing:
            index += 1
        return f"placement-{index}"


def migrate_workspace_payload(
    payload: Mapping[str, Any],
    *,
    source_key: str,
    card_hints: Mapping[str, CardLayoutHints] | None = None,
) -> DashboardWorkspace:
    """Migrate the actual Tur 9 sort_order/CardSize workspace schema to v2."""

    raw_schema = payload.get("schema_version")
    if raw_schema is not None:
        try:
            schema_version = int(raw_schema)
        except (TypeError, ValueError) as exc:
            raise DashboardWorkspaceMigrationError("Workspace schema_version okunamadı.") from exc
        if schema_version == WORKSPACE_SCHEMA_VERSION:
            return DashboardWorkspace.from_dict(payload, source_key=source_key, card_hints=card_hints)
        raise DashboardWorkspaceMigrationError(
            f"Desteklenmeyen workspace schema_version: {schema_version}"
        )

    try:
        format_version = int(payload.get("format_version", 1))
    except (TypeError, ValueError) as exc:
        raise DashboardWorkspaceMigrationError("Legacy workspace format_version okunamadı.") from exc
    if format_version != 1:
        raise DashboardWorkspaceMigrationError(
            f"Desteklenmeyen legacy workspace format_version: {format_version}"
        )

    raw_placements = payload.get("placements") or []
    if not isinstance(raw_placements, list):
        raise DashboardWorkspaceMigrationError("Legacy workspace placements list olmalıdır.")

    hints_index = card_hints or {}
    sortable: list[tuple[int, int, str, str, Mapping[str, Any]]] = []
    for index, raw in enumerate(raw_placements):
        if not isinstance(raw, Mapping):
            raise DashboardWorkspaceMigrationError("Legacy workspace placement object olmalıdır.")
        source_screen_id = str(raw.get("source_screen_id") or "").strip()
        card_id = str(raw.get("card_id") or "").strip()
        if not source_screen_id or not card_id:
            raise DashboardWorkspaceMigrationError(
                "Legacy workspace placement kaynak kimliği eksik."
            )
        try:
            sort_order = max(0, int(raw.get("sort_order") or 0))
        except (TypeError, ValueError):
            sort_order = 0
        sortable.append((sort_order, index, source_screen_id, card_id, raw))

    legacy_placements: list[DashboardCardPlacement] = []
    hints_by_placement: dict[str, CardLayoutHints] = {}
    for placement_index, (_, _, source_screen_id, card_id, raw) in enumerate(sorted(sortable), start=1):
        placement_id = f"placement-{placement_index}"
        hints = hints_index.get(_card_key(source_screen_id, card_id), CardLayoutHints())
        size = str(raw.get("size") or CardSize.MEDIUM.value).strip().lower()
        legacy_placements.append(
            DashboardCardPlacement(
                placement_id=placement_id,
                source_screen_id=source_screen_id,
                card_id=card_id,
                x=0,
                y=0,
                w=_bounded_legacy_width(size, hints, 12),
                h=hints.default_h,
            )
        )
        hints_by_placement[placement_id] = hints

    workspace = DashboardWorkspace(
        source_key=source_key,
        placements=pack_placements(legacy_placements, columns=12),
        workspace_id=str(payload.get("workspace_id") or "default"),
        layout=DashboardLayoutSettings(
            columns=12,
            row_height=54,
            gap=10,
            compact_mode=CompactMode.VERTICAL,
        ),
    )
    workspace._layout_hints = hints_by_placement
    workspace.validate()
    return workspace


class DashboardWorkspaceStore:
    """Persist validated user dashboard workspaces outside the STS database."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else default_workspace_root()

    def workspace_path(self, source: Any) -> Path:
        return self.root / f"{source_workspace_key(source)}.json"

    def backup_path(self, source: Any) -> Path:
        path = self.workspace_path(source)
        return path.with_name(f"{path.stem}.backup{path.suffix}")

    def load(
        self,
        source: Any,
        *,
        dashboard_items: Iterable[DashboardItem] | None = None,
        additional_card_keys: Iterable[str] = (),
        protected_source_ids: Iterable[str] = (),
    ) -> DashboardWorkspace:
        key = source_workspace_key(source)
        path = self.workspace_path(source)
        if not path.exists():
            return DashboardWorkspace(source_key=key)

        payload = self._read_payload(path)
        card_hints = _card_hints_index(dashboard_items)
        is_legacy = payload.get("schema_version") is None
        try:
            workspace = migrate_workspace_payload(
                payload,
                source_key=key,
                card_hints=card_hints,
            )
        except (DashboardWorkspaceMigrationError, LayoutValidationError) as exc:
            raise DashboardWorkspaceMigrationError(
                f"Dashboard workspace yüklenemedi: {path}"
            ) from exc

        removed_orphans = (
            workspace.prune_orphaned_placements(
                dashboard_items,
                additional_card_keys=additional_card_keys,
                protected_source_ids=protected_source_ids,
            )
            if dashboard_items is not None
            else []
        )
        if is_legacy or removed_orphans:
            self._write_backup(path, self.backup_path(source))
            self._write_atomic(path, workspace.to_dict())
        return workspace

    def save(self, source: Any, workspace: DashboardWorkspace) -> Path:
        key = source_workspace_key(source)
        if workspace.source_key != key:
            raise DashboardWorkspaceError("Workspace source_key veri kaynağıyla eşleşmiyor.")
        try:
            workspace.validate()
            payload = workspace.to_dict()
        except LayoutValidationError as exc:
            raise DashboardWorkspaceError("Geçersiz dashboard workspace kaydedilemez.") from exc

        path = self.workspace_path(source)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing_payload = self._read_payload(path)
            try:
                migrate_workspace_payload(
                    existing_payload,
                    source_key=key,
                    card_hints={
                        _card_key(placement.source_screen_id, placement.card_id): workspace._layout_hints[placement.placement_id]
                        for placement in workspace.placements
                        if placement.placement_id in workspace._layout_hints
                    },
                )
            except (DashboardWorkspaceMigrationError, LayoutValidationError) as exc:
                raise DashboardWorkspaceCorruptError(
                    f"Mevcut dashboard workspace geçersiz; overwrite edilmedi: {path}"
                ) from exc
            self._write_backup(path, self.backup_path(source))

        self._write_atomic(path, payload)
        return path

    @staticmethod
    def _read_payload(path: Path) -> Mapping[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise DashboardWorkspaceError(f"Dashboard workspace okunamadı: {path}") from exc
        except json.JSONDecodeError as exc:
            raise DashboardWorkspaceCorruptError(
                f"Dashboard workspace JSON bozuk; dosya korunuyor: {path}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise DashboardWorkspaceCorruptError(
                f"Dashboard workspace JSON object olmalıdır: {path}"
            )
        return payload

    @staticmethod
    def _write_backup(source_path: Path, backup_path: Path) -> None:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = backup_path.with_suffix(backup_path.suffix + ".tmp")
        try:
            with source_path.open("rb") as source_handle, temp_path.open("wb") as backup_handle:
                shutil.copyfileobj(source_handle, backup_handle)
                backup_handle.flush()
                os.fsync(backup_handle.fileno())
            os.replace(temp_path, backup_path)
            DashboardWorkspaceStore._fsync_directory(backup_path.parent)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            DashboardWorkspaceStore._fsync_directory(path.parent)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        try:
            directory_fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
