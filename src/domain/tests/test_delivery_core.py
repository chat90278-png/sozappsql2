from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from src.domain.delivery_core import (
    ACTUAL_DATE_LABEL,
    PLANNED_DATE_LABEL,
    add_months,
    as_number,
    assignable_remaining,
    build_delivery_info,
    distributable_target,
    fill_all_target,
    fill_remaining_target,
    fmt_num,
    is_delivered_status,
    planned_remaining_state,
    remaining_qty,
    split_evenly,
    validate_quantities,
    validate_status_rules,
    validate_unit_tracking,
)


def _status_errors(
    *,
    status="PLAN",
    actual="",
    planned_date="2026-06-TBD",
    planned=None,
    delivered=None,
):
    return validate_status_rules(
        status,
        actual,
        planned_date,
        {"A": 1.0} if planned is None else planned,
        {"A": 0.0} if delivered is None else delivered,
    )


def test_as_number_matches_delivery_dialog_conversion():
    assert as_number(3) == 3.0
    assert as_number("2.5") == 2.5
    assert as_number(None) == 0.0
    assert as_number("1,5") == 0.0
    assert as_number("bad") == 0.0


def test_fmt_num_matches_delivery_dialog_formatting():
    assert fmt_num(3.0) == "3"
    assert fmt_num(2.345) == "2.35"
    assert fmt_num(None) == "0"
    assert fmt_num("bad") == "bad"


def test_add_months_clamps_to_target_month_end():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert add_months(date(2026, 12, 15), 2) == date(2027, 2, 15)


def test_remaining_qty_matches_repeated_dialog_formula():
    assert remaining_qty(10, 3) == 7.0
    assert remaining_qty(3, 10) == 0
    assert remaining_qty("5.5", "1.25") == 4.25


def test_assignable_remaining_matches_delivery_dialog_formula_scenario_one():
    system_total = 12.0
    planned_assigned = 4.0
    current_planned = 3.0
    original_delivery_dialog = system_total - (planned_assigned + current_planned)
    assert assignable_remaining(system_total, planned_assigned, current_planned) == original_delivery_dialog


def test_assignable_remaining_matches_auto_accept_formula_scenario_one():
    system_total = 12.0
    existing_assigned = 4.0
    current_assigned = 3.0
    original_auto_accept = (system_total - existing_assigned) - current_assigned
    assert assignable_remaining(system_total, existing_assigned, current_assigned) == original_auto_accept


def test_assignable_remaining_matches_both_original_formulas_when_over_assigned():
    system_total = 5.0
    assigned_elsewhere = 4.0
    current_planned = 3.0
    delivery_formula = system_total - (assigned_elsewhere + current_planned)
    auto_accept_formula = (system_total - assigned_elsewhere) - current_planned
    result = assignable_remaining(system_total, assigned_elsewhere, current_planned)
    assert result == delivery_formula == auto_accept_formula == -2.0


def test_fill_all_and_fill_remaining_are_same_function_alias():
    assert fill_all_target is distributable_target
    assert fill_remaining_target is distributable_target
    assert fill_all_target(10, 4) == 6.0
    assert fill_remaining_target(10, 12) == 0


def test_is_delivered_status_combines_dialog_status_rules():
    assert is_delivered_status("Teslim Edildi") is True
    assert is_delivered_status("  teslim   edildi ") is True
    assert is_delivered_status("Tamamlandı") is True
    assert is_delivered_status("tamamlandi") is True
    assert is_delivered_status("PLAN") is False


def test_planned_remaining_state_matches_delivery_dialog_behavior():
    all_delivered, remaining = planned_remaining_state(
        {"A": 2, "B": 0, "C": 1},
        {"A": 2, "B": 0, "C": 0},
    )
    assert all_delivered is False
    assert remaining == ["C"]

    all_delivered, remaining = planned_remaining_state({"A": 2}, {"A": 2})
    assert all_delivered is True
    assert remaining == []

    all_delivered, remaining = planned_remaining_state({"A": 0}, {"A": 0})
    assert all_delivered is False
    assert remaining == []


def test_validate_quantities_returns_exact_delivery_dialog_messages():
    system_qty = {"A": 5, "B": 10}
    assigned_elsewhere = {"A": 2, "B": 0}
    errors = validate_quantities(
        ["A", "B"],
        {"A": 4, "B": 3},
        {"A": 1, "B": 4},
        system_qty.__getitem__,
        assigned_elsewhere.__getitem__,
    )
    assert errors == [
        "A: tanımlanan toplam miktar sistem adedini aşamaz.",
        "B: teslim edilen, teslim edilecekten büyük olamaz.",
    ]


def test_validate_quantities_accepts_valid_values():
    errors = validate_quantities(
        ["A"],
        {"A": 3},
        {"A": 2},
        lambda _comp: 10,
        lambda _comp: 4,
    )
    assert errors == []


# Rule 1: planned date required.
def test_status_rule_planned_date_required_negative():
    errors = _status_errors(planned_date="")
    assert (
        f"{PLANNED_DATE_LABEL} zorunludur. Kesin tarih yazabilir veya belirsizse "
        "TBD / YYYY-MM-TBD / YYYY-TBD-TBD kullanabilirsiniz."
    ) in errors


def test_status_rule_planned_date_required_positive():
    errors = _status_errors(planned_date="TBD")
    assert not any("zorunludur. Kesin tarih" in error for error in errors)


# Rule 2: planned date flexible format.
def test_status_rule_planned_date_format_negative():
    errors = _status_errors(planned_date="2026/06/10")
    assert (
        f"{PLANNED_DATE_LABEL}: Tarih YYYY-MM-DD, YYYY-MM-TBD, YYYY-TBD-TBD, TBD veya - olmalı."
        in errors
    )


def test_status_rule_planned_date_format_positive():
    errors = _status_errors(planned_date="2026-06-TBD")
    assert not any(error.startswith(f"{PLANNED_DATE_LABEL}:") for error in errors)


# Rule 3: actual date flexible format.
def test_status_rule_actual_date_format_negative():
    errors = _status_errors(actual="2026/06/10")
    assert (
        f"{ACTUAL_DATE_LABEL}: Tarih YYYY-MM-DD, YYYY-MM-TBD, YYYY-TBD-TBD, TBD veya - olmalı."
        in errors
    )


def test_status_rule_actual_date_format_positive():
    errors = _status_errors(actual="TBD")
    assert not any(error.startswith(f"{ACTUAL_DATE_LABEL}:") for error in errors)


# Rule 4: delivered status requires exact YYYY-MM-DD, TBD is not accepted.
def test_status_rule_delivered_exact_date_negative():
    errors = _status_errors(
        status="Teslim Edildi",
        actual="TBD",
        planned={"A": 1},
        delivered={"A": 1},
    )
    assert (
        f"Tamamlanan kayıtta {ACTUAL_DATE_LABEL} kesin YYYY-MM-DD olmalıdır. TBD kabul edilmez."
        in errors
    )


def test_status_rule_delivered_exact_date_positive():
    errors = _status_errors(
        status="Teslim Edildi",
        actual=date.today().isoformat(),
        planned={"A": 1},
        delivered={"A": 1},
    )
    assert not any("kesin YYYY-MM-DD olmalıdır" in error for error in errors)


# Rule 5: exact actual date cannot be in the future.
def test_status_rule_future_actual_date_negative():
    future = (date.today() + timedelta(days=1)).isoformat()
    errors = _status_errors(actual=future)
    assert f"{ACTUAL_DATE_LABEL} bugünden ileri olamaz." in errors


def test_status_rule_future_actual_date_positive():
    errors = _status_errors(actual=date.today().isoformat())
    assert f"{ACTUAL_DATE_LABEL} bugünden ileri olamaz." not in errors


# Rule 6: delivered status requires zero remaining for every active component.
def test_status_rule_delivered_requires_zero_remaining_negative():
    errors = _status_errors(
        status="Teslim Edildi",
        actual=date.today().isoformat(),
        planned={"A": 2, "B": 1},
        delivered={"A": 1, "B": 1},
    )
    assert (
        "Durum 'Teslim Edildi' olduğunda bu teslimattaki tüm bileşenlerin kalan değeri 0 olmalıdır.\n\n"
        "Eksik kalan bileşenler:\n• A"
    ) in errors


def test_status_rule_delivered_requires_zero_remaining_positive():
    errors = _status_errors(
        status="Teslim Edildi",
        actual=date.today().isoformat(),
        planned={"A": 2, "B": 1},
        delivered={"A": 2, "B": 1},
    )
    assert not any("Eksik kalan bileşenler" in error for error in errors)


# Rule 7: all remaining zero requires delivered status.
def test_status_rule_all_zero_requires_delivered_status_negative():
    errors = _status_errors(
        status="PLAN",
        planned={"A": 2},
        delivered={"A": 2},
    )
    assert (
        "Bu teslimatta tüm bileşenlerin kalanı 0. Kaydetmeden önce Durum alanını 'Teslim Edildi' yapın."
        in errors
    )


def test_status_rule_all_zero_requires_delivered_status_positive():
    errors = _status_errors(
        status="PLAN",
        planned={"A": 2},
        delivered={"A": 1},
    )
    assert not any("Durum Uyumsuz" in error for error in errors)
    assert not any("tüm bileşenlerin kalanı 0" in error for error in errors)


def test_status_rule_delivered_requires_actual_date_message_is_exact():
    errors = _status_errors(
        status="Tamamlandı",
        actual="",
        planned={"A": 1},
        delivered={"A": 1},
    )
    assert (
        f"Durum tamamlandı/teslim edildi olduğunda {ACTUAL_DATE_LABEL} zorunludur."
        in errors
    )


def test_validate_unit_tracking_rejects_fractional_planned_qty_with_exact_message():
    assert validate_unit_tracking("GÖVDE", 1.5, []) == (
        "Bu bileşende teslim edilecek adet tam sayı olmalıdır.\n(GÖVDE)"
    )


def test_validate_unit_tracking_rejects_duplicate_normalized_identifier():
    units = [
        {"slot_no": 1, "identifier": "TC-001"},
        {"slot_no": 2, "identifier": " tc-001 "},
    ]
    assert validate_unit_tracking("GÖVDE", 2, units) == (
        "GÖVDE: Aynı kuyruk no / seri no iki kez girilemez. Lütfen düzeltin."
    )


def test_validate_unit_tracking_accepts_unique_or_blank_identifiers():
    units = [
        {"slot_no": 1, "identifier": "TC-001"},
        {"slot_no": 2, "identifier": ""},
        {"slot_no": 3, "identifier": "TC-002"},
    ]
    assert validate_unit_tracking("GÖVDE", 3, units) is None


def test_split_evenly_matches_auto_accept_when_fully_divisible():
    assert split_evenly(12, 3) == [4.0, 4.0, 4.0]


def test_split_evenly_matches_auto_accept_when_not_divisible():
    assert split_evenly(10, 3) == [0.0, 0.0, 0.0]
    assert split_evenly(1.5, 3) == [0.0, 0.0, 0.0]


def test_split_evenly_matches_auto_accept_when_count_is_one():
    assert split_evenly(7, 1) == [7.0]


def test_split_evenly_non_positive_count_has_no_cards():
    assert split_evenly(10, 0) == []
    assert split_evenly(10, -2) == []


def test_build_delivery_info_populates_complete_delivery_info_field_list():
    units = {"A": [{"slot_no": 1, "identifier": "SN-1"}]}
    info = build_delivery_info(
        name="Kabul 1",
        status="Teslim Edildi",
        acceptance_date="2026-07-01",
        note="Not",
        planned={"A": 1},
        delivered={"A": 1},
        t0_date="2026-01-01",
        t0_months=6,
        completion_date="2026-07-01",
        delivery_user="Ayşe",
        planned_acceptance_date="2026-06-TBD",
        component_units=units,
        merge_uid="merge-123",
    )
    assert info.name == "Kabul 1"
    assert info.status == "Teslim Edildi"
    assert info.acceptance_date == "2026-07-01"
    assert info.note == "Not"
    assert info.planned == {"A": 1}
    assert info.delivered == {"A": 1}
    assert info.t0_date == "2026-01-01"
    assert info.t0_months == 6
    assert info.completion_date == "2026-07-01"
    assert info.delivery_user == "Ayşe"
    assert info.planned_acceptance_date == "2026-06-TBD"
    assert info.component_units == units
    assert info.merge_uid == "merge-123"


def test_build_delivery_info_preserves_current_dialog_merge_uid_default():
    info = build_delivery_info("Teslimat 1", "PLAN", "", "", {}, {})
    assert info.merge_uid == ""
    assert info.component_units == {}


def test_delivery_core_has_no_qt_dependency():
    source = Path(__file__).resolve().parents[1] / "delivery_core.py"
    text = source.read_text(encoding="utf-8")
    assert "PySide6" not in text
    assert "QWidget" not in text
    assert "QTableWidget" not in text
    assert "QMessageBox" not in text
