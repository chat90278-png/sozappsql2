from __future__ import annotations

from urllib.parse import quote


def _normalize_required_segment(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} boş olamaz.")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} boş olamaz.")
    return normalized


def _encode_segment(value: str) -> str:
    return quote(value, safe="-._~")


def build_agenda_key(
    *,
    provider_code: str,
    entity_type: str,
    entity_id: object,
    discriminator: object | None = None,
) -> str:
    provider = _normalize_required_segment(provider_code, "provider_code")
    entity = _normalize_required_segment(entity_type, "entity_type")
    entity_identifier = _normalize_required_segment(entity_id, "entity_id")

    segments = [provider, entity, entity_identifier]
    if discriminator is not None:
        normalized_discriminator = str(discriminator).strip()
        if normalized_discriminator:
            segments.append(normalized_discriminator)

    return ":".join(_encode_segment(segment) for segment in segments)
