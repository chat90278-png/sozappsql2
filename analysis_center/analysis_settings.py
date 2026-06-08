from __future__ import annotations

from .analysis_models import VisualSettings

DEFAULT_SETTINGS = VisualSettings(
    compact_mode=False,
    upcoming_days=60,
    max_table_rows=100,
    show_disabled_sections=True,
    empty_state_uses_sample=True,
)

ACTIVE_SCREEN_IDS = {
    "executive_summary",
    "platform_analysis",
    "contract_analysis",
    "acceptance_analysis",
    "deadline_analysis",
    "mini_data_health",
}

PHASE_2_SCREEN_IDS = {
    "system_analysis",
    "component_analysis",
    "tag_analysis",
    "user_analysis",
    "detailed_data_health",
}

NORMALIZED_DATA_KEYS = (
    "contracts",
    "platforms",
    "acceptances",
    "deadlines",
    "systems",
    "components",
    "users",
    "tags",
    "health_items",
)

COMPLETED_STATUS_KEYS = {
    "tamamlandi",
    "tamamlandı",
    "tamam",
    "kabul edildi",
    "kapatildi",
    "kapatıldı",
    "closed",
    "completed",
    "done",
}

NOT_STARTED_STATUS_KEYS = {
    "baslanmadi",
    "başlanmadı",
    "plan",
    "planlandi",
    "planlandı",
    "not started",
}

IN_PROGRESS_STATUS_KEYS = {
    "devam ediyor",
    "acik",
    "açık",
    "aktif",
    "open",
    "in progress",
}
