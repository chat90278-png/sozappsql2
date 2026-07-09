from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from .analysis_models import CardLayoutHints, ResizePolicy


class CompactMode(str, Enum):
    NONE = "none"
    VERTICAL = "vertical"


class DashboardLayoutError(ValueError):
    pass


class LayoutValidationError(DashboardLayoutError):
    pass


class PlacementNotFoundError(DashboardLayoutError):
    pass


class LockedPlacementError(DashboardLayoutError):
    pass


class ResizePolicyError(DashboardLayoutError):
    pass


@dataclass(frozen=True, slots=True)
class DashboardLayoutSettings:
    columns: int = 12
    row_height: int = 54
    gap: int = 10
    compact_mode: CompactMode = CompactMode.VERTICAL

    def __post_init__(self) -> None:
        if not isinstance(self.columns, int) or isinstance(self.columns, bool) or self.columns <= 0:
            raise LayoutValidationError("Dashboard kolon sayısı pozitif tam sayı olmalıdır.")
        if not isinstance(self.row_height, int) or isinstance(self.row_height, bool) or self.row_height <= 0:
            raise LayoutValidationError("Dashboard satır yüksekliği pozitif tam sayı olmalıdır.")
        if not isinstance(self.gap, int) or isinstance(self.gap, bool) or self.gap < 0:
            raise LayoutValidationError("Dashboard grid boşluğu negatif olamaz.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "row_height": self.row_height,
            "gap": self.gap,
            "compact_mode": self.compact_mode.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "DashboardLayoutSettings":
        raw = payload or {}
        try:
            compact_mode = CompactMode(str(raw.get("compact_mode") or CompactMode.VERTICAL.value))
        except ValueError as exc:
            raise LayoutValidationError("Desteklenmeyen dashboard compact_mode değeri.") from exc
        try:
            return cls(
                columns=int(raw.get("columns", 12)),
                row_height=int(raw.get("row_height", 54)),
                gap=int(raw.get("gap", 10)),
                compact_mode=compact_mode,
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, LayoutValidationError):
                raise
            raise LayoutValidationError("Dashboard layout ayarları geçersiz.") from exc


@dataclass(slots=True)
class DashboardCardPlacement:
    placement_id: str
    source_screen_id: str
    card_id: str
    x: int
    y: int
    w: int
    h: int
    locked: bool = False
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "placement_id": self.placement_id,
            "source_screen_id": self.source_screen_id,
            "card_id": self.card_id,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "locked": bool(self.locked),
            "settings": deepcopy(self.settings),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DashboardCardPlacement":
        placement_id = str(payload.get("placement_id") or "").strip()
        source_screen_id = str(payload.get("source_screen_id") or "").strip()
        card_id = str(payload.get("card_id") or "").strip()
        if not placement_id or not source_screen_id or not card_id:
            raise LayoutValidationError(
                "Dashboard placement_id, source_screen_id ve card_id alanlarını içermelidir."
            )
        settings = payload.get("settings") or {}
        if not isinstance(settings, Mapping):
            raise LayoutValidationError(f"Placement settings mapping olmalıdır: {placement_id}")
        try:
            return cls(
                placement_id=placement_id,
                source_screen_id=source_screen_id,
                card_id=card_id,
                x=int(payload.get("x")),
                y=int(payload.get("y")),
                w=int(payload.get("w")),
                h=int(payload.get("h")),
                locked=bool(payload.get("locked", False)),
                settings=dict(settings),
            )
        except (TypeError, ValueError) as exc:
            raise LayoutValidationError(f"Placement koordinatları geçersiz: {placement_id}") from exc


@dataclass(frozen=True, slots=True)
class MoveCard:
    placement_id: str
    from_x: int
    from_y: int
    to_x: int
    to_y: int


@dataclass(frozen=True, slots=True)
class ResizeCard:
    placement_id: str
    from_w: int
    from_h: int
    to_w: int
    to_h: int


@dataclass(frozen=True, slots=True)
class AddCard:
    placement: DashboardCardPlacement


@dataclass(frozen=True, slots=True)
class RemoveCard:
    placement: DashboardCardPlacement


DEFAULT_FALLBACK_HINTS = CardLayoutHints()


def placement_order(placement: DashboardCardPlacement) -> tuple[int, int, str]:
    return placement.y, placement.x, placement.placement_id


def placements_overlap(a: DashboardCardPlacement, b: DashboardCardPlacement) -> bool:
    return (
        a.x < b.x + b.w
        and a.x + a.w > b.x
        and a.y < b.y + b.h
        and a.y + a.h > b.y
    )


def colliding_placements(
    placement: DashboardCardPlacement,
    placements: Iterable[DashboardCardPlacement],
) -> list[DashboardCardPlacement]:
    return sorted(
        (
            other
            for other in placements
            if other.placement_id != placement.placement_id and placements_overlap(placement, other)
        ),
        key=placement_order,
    )


def first_available_position(
    placements: Iterable[DashboardCardPlacement],
    *,
    w: int,
    h: int,
    columns: int,
) -> tuple[int, int]:
    """Return the deterministic top-left free slot without moving existing cards."""

    if w <= 0 or h <= 0 or w > columns:
        raise LayoutValidationError("Yeni placement ölçüleri grid sınırları içinde olmalıdır.")
    items = list(placements)
    max_bottom = max((item.y + item.h for item in items), default=0)
    for y in range(max_bottom + 1):
        for x in range(columns - w + 1):
            probe = DashboardCardPlacement("__probe__", "__probe__", "__probe__", x, y, w, h)
            if not any(placements_overlap(probe, item) for item in items):
                return x, y
    return 0, max_bottom


def pack_placements(
    placements: Iterable[DashboardCardPlacement],
    *,
    columns: int,
) -> list[DashboardCardPlacement]:
    """Pack placements in the given order using deterministic row-major rows."""

    packed: list[DashboardCardPlacement] = []
    cursor_x = 0
    cursor_y = 0
    row_height = 0
    for source in placements:
        placement = deepcopy(source)
        if placement.w > columns:
            raise LayoutValidationError(f"Placement grid genişliğini aşıyor: {placement.placement_id}")
        if cursor_x and cursor_x + placement.w > columns:
            cursor_y += row_height
            cursor_x = 0
            row_height = 0
        placement.x = cursor_x
        placement.y = cursor_y
        packed.append(placement)
        cursor_x += placement.w
        row_height = max(row_height, placement.h)
        if cursor_x >= columns:
            cursor_y += row_height
            cursor_x = 0
            row_height = 0
    return packed


class DashboardLayoutEngine:
    """Pure-Python logical grid engine for deterministic dashboard layouts."""

    def __init__(self, settings: DashboardLayoutSettings | None = None):
        self.settings = settings or DashboardLayoutSettings()

    def validate(
        self,
        placements: Iterable[DashboardCardPlacement],
        hints_by_placement: Mapping[str, CardLayoutHints] | None = None,
    ) -> None:
        items = list(placements)
        hints = hints_by_placement or {}
        seen: set[str] = set()
        for placement in items:
            if not placement.placement_id:
                raise LayoutValidationError("placement_id boş olamaz.")
            if placement.placement_id in seen:
                raise LayoutValidationError(f"Tekrarlı placement_id: {placement.placement_id}")
            seen.add(placement.placement_id)
            if not placement.source_screen_id or not placement.card_id:
                raise LayoutValidationError(
                    f"Placement kaynak kimliği eksik: {placement.placement_id}"
                )
            for name in ("x", "y", "w", "h"):
                value = getattr(placement, name)
                if not isinstance(value, int) or isinstance(value, bool):
                    raise LayoutValidationError(
                        f"Placement {name} tam sayı olmalıdır: {placement.placement_id}"
                    )
            if placement.x < 0:
                raise LayoutValidationError(f"Placement x negatif olamaz: {placement.placement_id}")
            if placement.y < 0:
                raise LayoutValidationError(f"Placement y negatif olamaz: {placement.placement_id}")
            if placement.w <= 0:
                raise LayoutValidationError(f"Placement genişliği pozitif olmalıdır: {placement.placement_id}")
            if placement.h <= 0:
                raise LayoutValidationError(f"Placement yüksekliği pozitif olmalıdır: {placement.placement_id}")
            hint = hints.get(placement.placement_id, DEFAULT_FALLBACK_HINTS)
            self._validate_dimensions(placement, hint)
            if placement.x + placement.w > self.settings.columns:
                raise LayoutValidationError(
                    f"Placement kolon sınırını aşıyor: {placement.placement_id}"
                )

        ordered = sorted(items, key=placement_order)
        for index, placement in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if placements_overlap(placement, other):
                    raise LayoutValidationError(
                        f"Placement overlap: {placement.placement_id} / {other.placement_id}"
                    )

    def add(
        self,
        placements: Iterable[DashboardCardPlacement],
        placement: DashboardCardPlacement,
        *,
        hints_by_placement: Mapping[str, CardLayoutHints] | None = None,
        compact: bool | None = None,
    ) -> list[DashboardCardPlacement]:
        items = deepcopy(list(placements))
        if any(item.placement_id == placement.placement_id for item in items):
            raise LayoutValidationError(f"Tekrarlı placement_id: {placement.placement_id}")
        candidate = deepcopy(placement)
        hint = (hints_by_placement or {}).get(candidate.placement_id, DEFAULT_FALLBACK_HINTS)
        self._validate_dimensions(candidate, hint)
        self._clamp_position(candidate)
        items.append(candidate)
        resolved = self._resolve_push(items, candidate.placement_id)
        return self._finish(resolved, hints_by_placement, compact)

    def move(
        self,
        placements: Iterable[DashboardCardPlacement],
        *,
        placement_id: str,
        x: int,
        y: int,
        hints_by_placement: Mapping[str, CardLayoutHints] | None = None,
        compact: bool | None = None,
    ) -> list[DashboardCardPlacement]:
        items = deepcopy(list(placements))
        placement = self._find(items, placement_id)
        if placement.locked:
            raise LockedPlacementError(f"Locked placement taşınamaz: {placement_id}")
        placement.x = int(x)
        placement.y = int(y)
        self._clamp_position(placement)
        resolved = self._resolve_push(items, placement_id)
        return self._finish(resolved, hints_by_placement, compact)

    def resize(
        self,
        placements: Iterable[DashboardCardPlacement],
        *,
        placement_id: str,
        w: int,
        h: int,
        hints_by_placement: Mapping[str, CardLayoutHints] | None = None,
        compact: bool | None = None,
    ) -> list[DashboardCardPlacement]:
        items = deepcopy(list(placements))
        placement = self._find(items, placement_id)
        if placement.locked:
            raise LockedPlacementError(f"Locked placement resize edilemez: {placement_id}")
        hint = (hints_by_placement or {}).get(placement_id, DEFAULT_FALLBACK_HINTS)
        new_w = int(w)
        new_h = int(h)
        self._validate_resize_policy(placement, new_w, new_h, hint.resize_policy)
        placement.w = new_w
        placement.h = new_h
        self._validate_dimensions(placement, hint)
        self._clamp_position(placement)
        resolved = self._resolve_push(items, placement_id)
        return self._finish(resolved, hints_by_placement, compact)

    def remove(
        self,
        placements: Iterable[DashboardCardPlacement],
        *,
        placement_id: str,
        hints_by_placement: Mapping[str, CardLayoutHints] | None = None,
        compact: bool | None = None,
    ) -> list[DashboardCardPlacement]:
        items = deepcopy(list(placements))
        self._find(items, placement_id)
        items = [placement for placement in items if placement.placement_id != placement_id]
        return self._finish(items, hints_by_placement, compact)

    def compact(
        self,
        placements: Iterable[DashboardCardPlacement],
        *,
        hints_by_placement: Mapping[str, CardLayoutHints] | None = None,
    ) -> list[DashboardCardPlacement]:
        items = deepcopy(list(placements))
        if self.settings.compact_mode == CompactMode.NONE:
            self.validate(items, hints_by_placement)
            return sorted(items, key=placement_order)

        compacted: list[DashboardCardPlacement] = []
        for placement in sorted(items, key=placement_order):
            if not placement.locked:
                for target_y in range(placement.y + 1):
                    candidate = deepcopy(placement)
                    candidate.y = target_y
                    if not any(placements_overlap(candidate, other) for other in compacted):
                        placement.y = target_y
                        break
            compacted.append(placement)
        compacted.sort(key=placement_order)
        self.validate(compacted, hints_by_placement)
        return compacted

    def _finish(
        self,
        placements: list[DashboardCardPlacement],
        hints_by_placement: Mapping[str, CardLayoutHints] | None,
        compact: bool | None,
    ) -> list[DashboardCardPlacement]:
        should_compact = self.settings.compact_mode == CompactMode.VERTICAL if compact is None else compact
        result = self.compact(placements, hints_by_placement=hints_by_placement) if should_compact else placements
        result = sorted(result, key=placement_order)
        self.validate(result, hints_by_placement)
        return result

    def _resolve_push(
        self,
        placements: list[DashboardCardPlacement],
        primary_id: str,
    ) -> list[DashboardCardPlacement]:
        by_id = {placement.placement_id: placement for placement in placements}
        queue: deque[str] = deque([primary_id])
        queued = {primary_id}
        max_steps = max(100, len(placements) * len(placements) * 20)
        steps = 0

        while queue:
            active_id = queue.popleft()
            queued.discard(active_id)
            active = by_id[active_id]
            while True:
                collisions = colliding_placements(active, by_id.values())
                if not collisions:
                    break
                collider = collisions[0]
                if collider.locked:
                    if active.locked:
                        raise LayoutValidationError(
                            f"Locked placement overlap çözülemedi: {active.placement_id} / {collider.placement_id}"
                        )
                    active.y = collider.y + collider.h
                else:
                    collider.y = active.y + active.h
                    if collider.placement_id not in queued:
                        queue.append(collider.placement_id)
                        queued.add(collider.placement_id)
                steps += 1
                if steps > max_steps:
                    raise DashboardLayoutError("Dashboard collision reflow güvenlik sınırını aştı.")

        return sorted(by_id.values(), key=placement_order)

    def _clamp_position(self, placement: DashboardCardPlacement) -> None:
        if placement.w > self.settings.columns:
            raise LayoutValidationError(f"Placement grid genişliğini aşıyor: {placement.placement_id}")
        placement.x = max(0, min(placement.x, self.settings.columns - placement.w))
        placement.y = max(0, placement.y)

    @staticmethod
    def _find(
        placements: Iterable[DashboardCardPlacement],
        placement_id: str,
    ) -> DashboardCardPlacement:
        for placement in placements:
            if placement.placement_id == placement_id:
                return placement
        raise PlacementNotFoundError(f"Dashboard placement bulunamadı: {placement_id}")

    @staticmethod
    def _validate_dimensions(
        placement: DashboardCardPlacement,
        hint: CardLayoutHints,
    ) -> None:
        if placement.w < hint.min_w:
            raise LayoutValidationError(
                f"Placement min_w sınırının altında: {placement.placement_id}"
            )
        if placement.h < hint.min_h:
            raise LayoutValidationError(
                f"Placement min_h sınırının altında: {placement.placement_id}"
            )
        if hint.max_w is not None and placement.w > hint.max_w:
            raise LayoutValidationError(
                f"Placement max_w sınırını aşıyor: {placement.placement_id}"
            )
        if hint.max_h is not None and placement.h > hint.max_h:
            raise LayoutValidationError(
                f"Placement max_h sınırını aşıyor: {placement.placement_id}"
            )

    @staticmethod
    def _validate_resize_policy(
        placement: DashboardCardPlacement,
        new_w: int,
        new_h: int,
        policy: ResizePolicy,
    ) -> None:
        width_changed = new_w != placement.w
        height_changed = new_h != placement.h
        if policy == ResizePolicy.NONE and (width_changed or height_changed):
            raise ResizePolicyError(f"Placement resize kapalı: {placement.placement_id}")
        if policy in {ResizePolicy.FIXED_HEIGHT, ResizePolicy.HORIZONTAL} and height_changed:
            raise ResizePolicyError(f"Placement yüksekliği sabit: {placement.placement_id}")
        if policy in {ResizePolicy.FIXED_WIDTH, ResizePolicy.VERTICAL} and width_changed:
            raise ResizePolicyError(f"Placement genişliği sabit: {placement.placement_id}")
