from __future__ import annotations

import pytest

from src.domain.agenda.keys import build_agenda_key


def test_build_agenda_key_is_deterministic():
    first = build_agenda_key(provider_code="deadline", entity_type="contract", entity_id=42)
    second = build_agenda_key(provider_code="deadline", entity_type="contract", entity_id=42)

    assert first == second == "deadline:contract:42"


def test_build_agenda_key_strips_segment_whitespace():
    key = build_agenda_key(
        provider_code="  deadline  ",
        entity_type="  contract  ",
        entity_id="  42  ",
    )

    assert key == "deadline:contract:42"


def test_build_agenda_key_adds_discriminator():
    key = build_agenda_key(
        provider_code="activity",
        entity_type="contract",
        entity_id=42,
        discriminator=" completion_date ",
    )

    assert key == "activity:contract:42:completion_date"
    assert build_agenda_key(
        provider_code="activity",
        entity_type="contract",
        entity_id=42,
        discriminator="   ",
    ) == "activity:contract:42"


def test_build_agenda_key_rejects_empty_provider_code():
    with pytest.raises(ValueError):
        build_agenda_key(provider_code="   ", entity_type="contract", entity_id=42)


def test_build_agenda_key_rejects_empty_entity_type():
    with pytest.raises(ValueError):
        build_agenda_key(provider_code="deadline", entity_type="   ", entity_id=42)


def test_build_agenda_key_rejects_missing_entity_id():
    with pytest.raises(ValueError):
        build_agenda_key(provider_code="deadline", entity_type="contract", entity_id=None)

    with pytest.raises(ValueError):
        build_agenda_key(provider_code="deadline", entity_type="contract", entity_id="   ")


def test_build_agenda_key_percent_encodes_separator_and_special_characters():
    colon_key = build_agenda_key(provider_code="deadline", entity_type="contract", entity_id="a:b")
    special_key = build_agenda_key(
        provider_code="deadline",
        entity_type="contract",
        entity_id="İş / %",
    )

    assert colon_key == "deadline:contract:a%3Ab"
    assert colon_key != "deadline:contract:a:b"
    assert special_key == "deadline:contract:%C4%B0%C5%9F%20%2F%20%25"
    assert "%2F" in special_key
    assert "%25" in special_key
    assert "%20" in special_key
    assert "%C4%B0%C5%9F" in special_key


def test_build_agenda_key_does_not_apply_locale_case_conversion():
    key = build_agenda_key(provider_code="DeadLine", entity_type="Contract", entity_id="İD")

    assert key == "DeadLine:Contract:%C4%B0D"
    assert key.startswith("DeadLine:Contract:")
