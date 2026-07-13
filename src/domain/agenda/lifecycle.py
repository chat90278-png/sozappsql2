from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from src.domain.agenda.constants import AgendaLifecycleType, AgendaSeverity
from src.domain.agenda.models import AgendaItem, AgendaItemState
from src.domain.agenda.priority import severity_rank


_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_timestamp(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, _TIMESTAMP_FORMAT)
    except ValueError:
        try:
            return datetime.fromisoformat(text).replace(tzinfo=None)
        except ValueError:
            return None


def _resurface_item(item: AgendaItem, state: AgendaItemState | None, now: datetime) -> AgendaItem:
    raw_interval = item.detail_payload.get("resurface_interval_days")
    if isinstance(raw_interval, bool):
        return item
    try:
        interval = int(raw_interval)
    except (TypeError, ValueError):
        return item
    if interval <= 0:
        return item
    anchor = None
    if state is not None:
        anchor = _parse_timestamp(state.first_presented_at) or _parse_timestamp(state.created_at)
    if anchor is None:
        anchor = now
    elapsed_days = max(0, (now.date() - anchor.date()).days)
    cycle = elapsed_days // interval
    effective_version = f"{item.version}|R{interval}:{cycle}"
    return item if effective_version == item.version else replace(item, version=effective_version)


@dataclass(frozen=True)
class AgendaLifecycleDecision:
    item: AgendaItem
    state: AgendaItemState | None
    visible: bool
    is_new: bool
    is_seen: bool
    is_snoozed: bool
    reason: str


class AgendaLifecycleEngine:
    def evaluate(
        self,
        item: AgendaItem,
        state: AgendaItemState | None,
        now: datetime,
    ) -> AgendaLifecycleDecision:
        current_now = now.replace(tzinfo=None)
        if item.lifecycle_type == AgendaLifecycleType.CONDITION:
            return self._evaluate_condition(_resurface_item(item, state, current_now), state, current_now)
        if item.lifecycle_type == AgendaLifecycleType.EVENT:
            return self._evaluate_event(item, state, current_now)
        return AgendaLifecycleDecision(item, state, False, False, False, False, "unsupported_lifecycle")

    def _evaluate_condition(
        self,
        item: AgendaItem,
        state: AgendaItemState | None,
        now: datetime,
    ) -> AgendaLifecycleDecision:
        break_reason = ""
        if state is not None and item.supports_snooze and state.snoozed_until:
            until = _parse_timestamp(state.snoozed_until)
            try:
                saved_rank = severity_rank(AgendaSeverity(str(state.snoozed_severity or "").strip()))
            except (TypeError, ValueError):
                saved_rank = None
            current_rank = severity_rank(item.severity)
            if until is None:
                break_reason = "snooze_timestamp_invalid"
            elif until <= now:
                break_reason = "snooze_expired"
            elif state.snoozed_version != item.version:
                break_reason = "snooze_version_changed"
            elif saved_rank is None:
                break_reason = "snooze_severity_invalid"
            elif current_rank > saved_rank:
                break_reason = "snooze_severity_increased"
            else:
                return AgendaLifecycleDecision(item, state, False, False, False, True, "snoozed")

        is_seen = bool(state is not None and state.seen_version == item.version)
        return AgendaLifecycleDecision(
            item=item,
            state=state,
            visible=True,
            is_new=not is_seen,
            is_seen=is_seen,
            is_snoozed=False,
            reason=break_reason or ("seen" if is_seen else "new"),
        )

    def _evaluate_event(
        self,
        item: AgendaItem,
        state: AgendaItemState | None,
        now: datetime,
    ) -> AgendaLifecycleDecision:
        if state is not None and state.dismissed_version == item.version:
            return AgendaLifecycleDecision(item, state, False, False, False, False, "dismissed")

        invalid_seen_timestamp = False
        if state is not None and state.seen_version == item.version:
            seen_at = _parse_timestamp(state.seen_at)
            if seen_at is not None:
                if now - seen_at < timedelta(hours=24):
                    return AgendaLifecycleDecision(item, state, True, False, True, False, "event_seen")
                return AgendaLifecycleDecision(
                    item, state, False, False, True, False, "event_seen_ttl_expired"
                )
            invalid_seen_timestamp = True

        event_at = _parse_timestamp(item.event_at)
        if event_at is None:
            return AgendaLifecycleDecision(
                item, state, False, False, False, False, "event_timestamp_invalid"
            )
        if now - event_at >= timedelta(days=7):
            return AgendaLifecycleDecision(
                item, state, False, False, False, False, "event_unseen_ttl_expired"
            )
        reason = "event_seen_timestamp_invalid" if invalid_seen_timestamp else "event_new"
        return AgendaLifecycleDecision(item, state, True, True, False, False, reason)
