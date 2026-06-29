# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import re
from datetime import date, datetime
from typing import List, Optional

from src import auth
from src.domain.flexible_date import is_tbd_contract_no
from src.models.app_models import ContractInfo
from src.services.excel_store import ExcelStore, add_months, parse_iso_date
from src.ui.dialogs.styled_dialog import StyledDialog
from src.ui.date_picker import build_date_input
from src.ui.widgets.user_select import MultiUserSelectWidget, MultiStaffSelectWidget, MultiPlatformSelectWidget
from src.ui.widgets.platform_select import PlatformSelectWidget
from src.ui.widgets.platform_tabs import PlatformTabsWidget, FixedContractTypeField

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QSpinBox, QMessageBox, QFrame, QScrollArea,
    QSizePolicy, QTextEdit,
)


def form_label(txt):
    l = QLabel(txt)
    l.setObjectName("formLabel")
    return l

class ContractDialog(StyledDialog):
    def __init__(self, store: ExcelStore, parent=None):
        super().__init__("Yeni Sözleşme", parent)
        self.store = store
        self.user_records = store.load_users()
        self.user_to_yi_yd = {u.get("name", ""): u.get("yi_yd", "Yİ") for u in self.user_records}
        self.current_staff = getattr(parent, "current_staff", None) if parent is not None else auth.current_staff
        self.staff_records = store.list_staff_for_engineer_selection() if hasattr(store, "list_staff_for_engineer_selection") else []
        self.result: Optional[ContractInfo] = None
        self._sd_verified_info: Optional[dict] = None
        self._sd_anchor_start_row: int = 0
        self._sd_anchor_end_row: int = 0
        self._sd_anchor_platform: str = ""
        self._sd_anchor_no: str = ""
        self._default_size = QSize(820, 600)
        self._normal_no_before_tbd = ""
        self.build()
        self._resize_to_safe_default()

    def build(self):
        root = QVBoxLayout(self)
        title = QLabel("Yeni Sözleşme")
        title.setObjectName("dialogTitle")
        root.addWidget(title)
        desc = QLabel("Ana sözleşme bilgilerini girin. SD kayıtları ana sözleşme detay ekranından eklenecek.")
        desc.setObjectName("muted")
        root.addWidget(desc)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.platform = MultiPlatformSelectWidget(self)
        self.platform.set_platforms(
            self.store.load_platforms() if hasattr(self.store, "load_platforms") else self.store.platform_names()
        )

        self.no = QLineEdit()
        self.no.setPlaceholderText("Örn: SZL-2026-001")

        # Sözleşme No satırı: input + SD doğrula + No bilinmiyor + inline uyarı.
        no_container = QWidget(self)
        no_container_lay = QVBoxLayout(no_container)
        no_container_lay.setContentsMargins(0, 0, 0, 0)
        no_container_lay.setSpacing(2)
        no_row = QWidget(no_container)
        no_lay = QHBoxLayout(no_row)
        no_lay.setContentsMargins(0, 0, 0, 0)
        no_lay.setSpacing(6)
        no_lay.addWidget(self.no, 1)

        self.verify_btn = QPushButton("Doğrula")
        self.verify_btn.setObjectName("secondary")
        self.verify_btn.setMinimumHeight(34)
        no_lay.addWidget(self.verify_btn, 0)

        self.unknown_no_btn = QPushButton("Sözleşme Yok")
        self.unknown_no_btn.setObjectName("secondary")
        self.unknown_no_btn.setCheckable(True)
        self.unknown_no_btn.setCursor(Qt.PointingHandCursor)
        self.unknown_no_btn.setMinimumHeight(34)
        self.unknown_no_btn.setToolTip("Sözleşme numarası bilinmiyorsa geçici TBD numarası üretir.")
        no_lay.addWidget(self.unknown_no_btn, 0)

        self.no_dup_warn = QLabel("")
        self.no_dup_warn.setStyleSheet("color:#dc2626; font-size:11px; font-weight:700; padding:0px;")
        self.no_dup_warn.setWordWrap(True)
        self.no_dup_warn.setVisible(False)
        no_container_lay.addWidget(no_row)
        no_container_lay.addWidget(self.no_dup_warn)

        self.user = MultiUserSelectWidget(self)
        self.user.set_available_users([u.get("name", "") for u in self.user_records])
        self.yi_yd = QLineEdit()
        self.yi_yd.setReadOnly(True)
        self.yi_yd.setText("Yİ")

        self.responsible_engineers = MultiStaffSelectWidget(self)
        self.responsible_engineers.set_staff_options(self.staff_records)

        # Normal sözleşme girişinde 1. foto davranışı: Ana Sözleşme varsayılan.
        self.ctype = FixedContractTypeField("Ana Sözleşme", self)
        self.ctype.setCurrentText("Ana Sözleşme")

        self.sd_code = QLineEdit()
        self.sd_code.setPlaceholderText("SD-1")
        self.sd_code.setEnabled(False)

        self.sig, self.sig_wrap = build_date_input(self, events_provider=self.date_picker_events)
        self.t0, self.t0_wrap = build_date_input(self, events_provider=self.date_picker_events)
        self.months = QSpinBox()
        self.months.setRange(0, 600)
        self.months.setSuffix(" ay")
        self.months.setValue(0)
        self.completion = QLineEdit()
        self.completion.setReadOnly(True)
        self.completion.setPlaceholderText("T0 + Ay ile otomatik hesaplanır (Termin)")

        self.note = QLineEdit()
        self.note.setPlaceholderText("Not")

        self.user.changed.connect(self._on_user_selection_changed)
        self.ctype.currentTextChanged.connect(self.on_contract_type_changed)
        self.verify_btn.clicked.connect(lambda: self.verify_sd_reference(show_message=False))
        self.platform.currentTextChanged.connect(self.on_sd_ref_changed)
        self.no.textChanged.connect(self.on_sd_ref_changed)
        self.no.textChanged.connect(lambda _text: self._sync_contract_type_display())
        self.no.editingFinished.connect(self._check_no_duplicate)
        self.platform.currentIndexChanged.connect(lambda _: self._check_no_duplicate())
        self.ctype.currentIndexChanged.connect(lambda _: self._check_no_duplicate())
        self.t0.textChanged.connect(self.update_completion_date)
        self.months.valueChanged.connect(self.update_completion_date)
        self.unknown_no_btn.toggled.connect(self.on_unknown_no_toggled)
        self.unknown_no_btn.toggled.connect(self._refresh_unknown_contract_button_style)
        QTimer.singleShot(0, self._refresh_unknown_contract_button_style)

        def add_field(label: str, widget, row: int, col: int):
            grid.addWidget(form_label(label), row * 2, col)
            grid.addWidget(widget, row * 2 + 1, col)

        # 1. foto ana yapı: sadece Platform ile Sözleşme No yer değiştirdi.
        add_field("Platform", self.platform, 0, 0)
        add_field("Sözleşme No", no_container, 0, 1)
        add_field("Sözleşmenin Sahibi Kullanıcı", self.user, 1, 0)
        add_field("Sorumlu Mühendis", self.responsible_engineers, 1, 1)
        add_field("Sözleşme Tipi", self.ctype, 2, 0)
        add_field("İmza Tarihi", self.sig_wrap, 2, 1)
        root.addLayout(grid)

        self.timeline_card = QFrame(self)
        self.timeline_card.setObjectName("subtleCard")
        self.timeline_card.setStyleSheet(
            "QFrame#subtleCard{background:#F8FBFF;border:1px solid #D8E6F5;border-radius:10px;}"
        )
        tl = QGridLayout(self.timeline_card)
        tl.setContentsMargins(10, 8, 10, 8)
        tl.setHorizontalSpacing(8)
        tl.setVerticalSpacing(4)
        tl.addWidget(form_label("T0 Başlangıç"), 0, 0)
        tl.addWidget(form_label("T0+Ay"), 0, 2)
        tl.addWidget(form_label("Termin Tarihi"), 0, 4)
        tl.addWidget(self.t0_wrap, 1, 0)
        plus = QLabel("+")
        plus.setAlignment(Qt.AlignCenter)
        tl.addWidget(plus, 1, 1)
        tl.addWidget(self.months, 1, 2)
        eq = QLabel("=")
        eq.setAlignment(Qt.AlignCenter)
        tl.addWidget(eq, 1, 3)
        tl.addWidget(self.completion, 1, 4)
        tl.setColumnStretch(0, 2)
        tl.setColumnStretch(2, 1)
        tl.setColumnStretch(4, 2)
        root.addWidget(self.timeline_card)

        root.addWidget(form_label("Not"))
        root.addWidget(self.note)

        self.sd_verify_hint = QLabel("")
        self.sd_verify_hint.setObjectName("muted")
        self.sd_verify_hint.setVisible(False)
        root.addWidget(self.sd_verify_hint)

        self.update_user_yi_yd()
        self.on_contract_type_changed()
        QTimer.singleShot(0, self._sync_contract_type_display)
        self.update_completion_date()

        row = QHBoxLayout()
        row.addStretch()
        save = QPushButton("Devam Et")
        save.clicked.connect(self.save)
        row.addWidget(save)
        root.addLayout(row)

    def _is_unknown_no_mode(self) -> bool:
        return bool(getattr(self, "unknown_no_btn", None) and self.unknown_no_btn.isChecked())

    def on_unknown_no_toggled(self, checked: bool):
        if checked:
            self._normal_no_before_tbd = self.no.text().strip()
            if not self.fill_unknown_contract_no():
                self.unknown_no_btn.blockSignals(True)
                self.unknown_no_btn.setChecked(False)
                self.unknown_no_btn.blockSignals(False)
                self._set_date_inputs_visible(True)
                return
            self._set_date_inputs_visible(False)
        else:
            if self.no.text().strip().upper().find("TBD") >= 0:
                self.no.setText(self._normal_no_before_tbd or "")
            self.no_dup_warn.setVisible(False)
            self._set_date_inputs_visible(True)
            self.update_completion_date()
        QTimer.singleShot(0, self._resize_to_safe_default)
        self._refresh_unknown_contract_button_style()

    def _set_date_inputs_visible(self, visible: bool):
        """Sözleşme Yok modunda tarih ve sözleşme tipi satırını tamamen sakla.

        Normal modda eski ana sözleşme formu görünür:
        - Sözleşme Tipi = Ana Sözleşme
        - İmza Tarihi / T0 / T0+Ay / Termin Tarihi görünür

        Sözleşme Yok modunda:
        - Sözleşme Tipi alanı gizlenir ve kayıt değeri '-' olur
        - İmza Tarihi label/input kalıntısı görünmez
        - T0 kartı görünmez
        """
        # Alan değerini moda göre sabitle.
        ctype = getattr(self, "ctype", None)
        try:
            if ctype is not None:
                if hasattr(ctype, "setText"):
                    ctype.setText("Ana Sözleşme" if visible else "-")
                elif hasattr(ctype, "setCurrentText"):
                    ctype.setCurrentText("Ana Sözleşme" if visible else "-")
        except Exception:
            pass

        # Widgetları göster/gizle. Silme yok; PySide deleted-object hatası oluşmasın.
        for widget in (
            getattr(self, "sig_wrap", None),
            getattr(self, "timeline_card", None),
            getattr(self, "ctype", None),
        ):
            if widget is not None:
                try:
                    widget.setVisible(visible)
                except Exception:
                    pass

        # add_field ile oluşturulan label referansları eski kodda tutulmuyor olabilir.
        # Bu yüzden sadece bu dialog altındaki label metinlerine göre güvenli gizleme yapıyoruz.
        hide_labels_when_unknown = {"İmza Tarihi", "Sözleşme Tipi"}
        for label in self.findChildren(QLabel):
            try:
                text = str(label.text() or "").strip()
            except Exception:
                continue
            if text in hide_labels_when_unknown:
                label.setVisible(visible)

        # Gizleme sonrası layoutu sıkıştır.
        try:
            layout = self.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()
            self.adjustSize()
        except Exception:
            pass
    def _refresh_unknown_contract_button_style(self, *_args):
        btn = getattr(self, "unknown_no_btn", None)
        if btn is None:
            return
        try:
            active = bool(btn.isChecked())
        except Exception:
            active = False
        if active:
            btn.setStyleSheet(
                "QPushButton{background:#2563eb;color:#0f172a;border:1px solid #1d4ed8;"
                "border-radius:8px;padding:6px 14px;font-weight:900;}"
                "QPushButton:hover{background:#1d4ed8;}"
                "QPushButton:pressed{background:#1e40af;}"
            )
        else:
            btn.setStyleSheet(
                "QPushButton{background:#f8fafc;color:#0f172a;border:1px solid #cbd5e1;"
                "border-radius:8px;padding:6px 14px;font-weight:900;}"
                "QPushButton:hover{background:#eef2f7;border-color:#93c5fd;}"
                "QPushButton:pressed{background:#dbeafe;}"
            )

    def fill_unknown_contract_no(self) -> bool:
        platform = self.platform.currentText().strip()
        if not platform:
            self.no_dup_warn.setText("Geçici sözleşme numarası oluşturmak için önce platform seçin.")
            self.no_dup_warn.setVisible(True)
            return False
        pattern = re.compile(rf"^\s*{re.escape(platform)}\s*-\s*TBD\s*-\s*(\d+)\s*$", re.IGNORECASE)
        max_n = 0
        try:
            for ex in self.store.list_main_contracts(platform):
                m = pattern.match(str(ex.get("no", "") or ""))
                if m:
                    max_n = max(max_n, int(m.group(1)))
        except Exception:
            pass
        self.no.setText(f"{platform} - TBD - {max_n + 1}")
        self._sync_contract_type_display()
        self.no_dup_warn.setVisible(False)
        self._refresh_unknown_contract_button_style()
        return True

    def _is_unknown_contract_no_mode(self) -> bool:
        btn = getattr(self, "unknown_no_btn", None)
        try:
            if btn is not None and hasattr(btn, "isChecked") and btn.isChecked():
                return True
        except Exception:
            pass
        return is_tbd_contract_no(self.no.text() if hasattr(self, "no") else "")

    def _contract_type_value(self) -> str:
        return "-" if self._is_unknown_contract_no_mode() else "Ana Sözleşme"

    def _sync_contract_type_display(self):
        if hasattr(self, "ctype"):
            try:
                self.ctype.setCurrentText(self._contract_type_value())
            except Exception:
                try:
                    self.ctype.setText(self._contract_type_value())
                except Exception:
                    pass

    def _resize_to_safe_default(self):
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        hint = self.minimumSizeHint()
        size_hint = self.sizeHint()
        if self._is_unknown_no_mode():
            base_h = 460
        else:
            base_h = self._default_size.height()
        target = QSize(
            max(self._default_size.width(), hint.width(), size_hint.width()),
            max(base_h, hint.height(), size_hint.height()),
        )
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry().size()
            target.setWidth(min(target.width(), max(720, available.width() - 80)))
            target.setHeight(min(target.height(), max(460, available.height() - 100)))
        self.resize(target)

    def _on_user_selection_changed(self):
        self.update_user_yi_yd()
        QTimer.singleShot(0, self._resize_for_user_selection)

    def _resize_for_user_selection(self):
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        self.user.updateGeometry()
        hint = self.minimumSizeHint()
        preferred_height = max(self._default_size.height(), self.sizeHint().height(), hint.height())
        screen = QApplication.primaryScreen()
        if screen is not None:
            available_height = screen.availableGeometry().height() - 80
            if available_height >= hint.height():
                preferred_height = min(preferred_height, available_height)
        self.resize(max(self.width(), self._default_size.width(), hint.width()), preferred_height)

    def is_sd_mode(self) -> bool:
        try:
            return self.ctype.currentText().strip() == "Sözleşme Değişikliği"
        except Exception:
            return False

    def on_sd_ref_changed(self):
        self._sd_verified_info = None
        self._sd_anchor_start_row = 0
        self._sd_anchor_end_row = 0
        self._sd_anchor_platform = ""
        self._sd_anchor_no = ""
        if self.is_sd_mode():
            suggested = self.store.next_sd_code(self.platform.currentText(), self.no.text().strip())
            if not self.sd_code.text().strip():
                self.sd_code.setText(suggested)
            self.sd_verify_hint.setText("Doğrulama bekleniyor.")
            self.sd_verify_hint.setStyleSheet("color:#64748b; font-weight:700;")

    def on_contract_type_changed(self):
        sd = self.is_sd_mode()
        self.sd_code.setEnabled(sd)
        self.verify_btn.setVisible(sd)
        if hasattr(self, "sd_label"):
            self.sd_label.setVisible(sd)
        self.sd_code.setVisible(sd)
        self.sd_verify_hint.setVisible(sd)
        if sd:
            self.no.setPlaceholderText("Mevcut kontrat no")
            if not self.sd_code.text().strip():
                self.sd_code.setText(self.store.next_sd_code(self.platform.currentText(), self.no.text().strip()))
            self.sd_verify_hint.setText("Doğrulama bekleniyor.")
            self.sd_verify_hint.setStyleSheet("color:#64748b; font-weight:700;")
            self.user.setEnabled(False)
            self.yi_yd.setReadOnly(True)
        else:
            self.no.setPlaceholderText("Örn: SZL-2026-001")
            self.sd_code.clear()
            self.sd_verify_hint.clear()
            self.sd_verify_hint.setStyleSheet("")
            self._sd_verified_info = None
            self._sd_anchor_start_row = 0
            self._sd_anchor_end_row = 0
            self._sd_anchor_platform = ""
            self._sd_anchor_no = ""
            self.user.setEnabled(True)
            self.update_user_yi_yd()
        self._sync_contract_type_display()

    def _set_user_from_main_contract(self, info: dict):
        target_user = str(info.get("user", "") or "").strip()
        if target_user:
            cur = self.user.selected_users()
            if target_user not in cur:
                cur = [target_user]
            self.user.set_users(cur)
        yi_yd = str(info.get("yi_yd", "Yİ") or "Yİ").strip().upper()
        self.yi_yd.setText("YD" if yi_yd == "YD" else "Yİ")

    def verify_sd_reference(self, show_message: bool = True) -> bool:
        if not self.is_sd_mode():
            return True
        no = self.no.text().strip()
        platform = self.platform.currentText().strip()
        if not no or not platform:
            if show_message:
                QMessageBox.warning(self, "Eksik", "Önce platform ve kontrat no girin.")
            self.sd_verify_hint.setText("Önce platform ve kontrat no girin.")
            self.sd_verify_hint.setStyleSheet("color:#b91c1c; font-weight:700;")
            return False
        info = self.store.find_main_contract_info(platform, no)
        if not info:
            if show_message:
                QMessageBox.warning(self, "Bulunamadı", "Bu platformda girilen kontrat no için Ana Sözleşme bulunamadı.")
            self._sd_verified_info = None
            self._sd_anchor_start_row = 0
            self._sd_anchor_end_row = 0
            self._sd_anchor_platform = ""
            self._sd_anchor_no = ""
            self.sd_verify_hint.setText("✗ Ana sözleşme bulunamadı.")
            self.sd_verify_hint.setStyleSheet("color:#b91c1c; font-weight:700;")
            return False
        self._sd_verified_info = info
        self._sd_anchor_start_row = int(info.get("block_start") or info.get("row") or 0)
        self._sd_anchor_end_row = int(info.get("block_end") or self._sd_anchor_start_row or 0)
        self._sd_anchor_platform = str(platform or "")
        self._sd_anchor_no = str(no or "")
        self._set_user_from_main_contract(info)
        self.sd_code.setText(self.store.next_sd_code(platform, no))
        self.sd_verify_hint.setText(f"✓ Ana sözleşme bulundu: {no}")
        self.sd_verify_hint.setStyleSheet("color:#047857; font-weight:800;")
        if show_message:
            QMessageBox.information(self, "Doğrulandı", f"Ana sözleşme bulundu. SD kaydı {no} kontrat no altında eklenecek.")
        return True

    def update_completion_date(self):
        if self._is_unknown_no_mode():
            if hasattr(self, "completion"):
                self.completion.clear()
            return
        t0 = parse_iso_date(self.t0.text().strip()) if hasattr(self, "t0") else None
        if not t0:
            self.completion.clear()
            return
        try:
            comp = add_months(t0, int(self.months.value()))
            self.completion.setText(comp.isoformat())
        except Exception:
            self.completion.clear()

    def date_picker_events(self) -> List[dict]:
        events = []
        for label, widget, kind in (
            ("İmza Tarihi", getattr(self, "sig", None), "signature"),
            ("T0 Başlangıç", getattr(self, "t0", None), "t0"),
            ("Termin Tarihi", getattr(self, "completion", None), "completion"),
        ):
            try:
                text = widget.text().strip() if widget is not None else ""
                d = parse_iso_date(text)
                if d:
                    events.append({"date": d.isoformat(), "title": label, "type": kind})
            except Exception:
                continue
        return events

    def update_user_yi_yd(self):
        if self.is_sd_mode() and self._sd_verified_info:
            self._set_user_from_main_contract(self._sd_verified_info)
            return
        selected = (self.user.selected_users() or [""])[0].strip()
        yi_yd = self.user_to_yi_yd.get(selected, "Yİ")
        self.yi_yd.setText("YD" if str(yi_yd).upper() == "YD" else "Yİ")

    def _normalized_sd_code(self) -> str:
        raw = str(self.sd_code.text() or "").strip().upper().replace(" ", "")
        if not raw:
            return ""
        m = re.match(r"^SD[-_]?(\d+)$", raw)
        if m:
            return f"SD-{int(m.group(1))}"
        return ""

    def _check_no_duplicate(self):
        """Sözleşme no + platform + tip kombinasyonu zaten varsa kırmızı uyarı göster."""
        if not hasattr(self, 'no_dup_warn'):
            return
        no = self.no.text().strip()
        platform = self.platform.currentText().strip()
        if not no or not platform:
            self.no_dup_warn.setVisible(False)
            self.no.setStyleSheet("")
            return
        contract_type = self._contract_type_value()
        if self.is_sd_mode():
            sd = self._normalized_sd_code()
            contract_type = sd if sd else self.sd_code.text().strip()
        try:
            existing = self.store.list_main_contracts(platform)
            for ex in existing:
                ex_no = self.store._normalize_label(str(ex.get("no", "") or "").strip())
                ex_type = self.store._normalize_label(str(ex.get("type", "") or "").strip())
                if (ex_no == self.store._normalize_label(no) and
                        ex_type == self.store._normalize_label(contract_type)):
                    self.no_dup_warn.setText(
                        f"⚠  '{platform}' platformunda bu sözleşme no zaten mevcut!"
                    )
                    self.no_dup_warn.setVisible(True)
                    self.no.setStyleSheet(
                        "QLineEdit{border:1.5px solid #dc2626; background:#fff5f5;}"
                    )
                    return
        except Exception:
            pass
        self.no_dup_warn.setVisible(False)
        self.no.setStyleSheet("")

    def _highlight_required(self, widget, error: bool):
        """Zorunlu alan boşsa kırmızı çerçeve, doluysa normal."""
        if error:
            widget.setStyleSheet("QLineEdit{border:1.5px solid #dc2626; background:#fff5f5;}"
                                 "QSpinBox{border:1.5px solid #dc2626; background:#fff5f5;}")
        else:
            widget.setStyleSheet("")

    def selected_platform_ids(self) -> List[int]:
        return self.platform.selected_platform_ids() if hasattr(self.platform, "selected_platform_ids") else []

    def _confirm_empty_responsible_engineer(self) -> bool:
        return True

    def save(self):
        self._sync_contract_type_display()
        unknown_mode = self._is_unknown_no_mode()
        if not self.no.text().strip():
            QMessageBox.warning(self, "Eksik", "Sözleşme no girin.")
            return
        if not self.platform.selected_platforms():
            QMessageBox.warning(self, "Eksik", "Lütfen en az bir platform seçiniz.")
            return
        if self.is_sd_mode() and not self.verify_sd_reference(show_message=False):
            QMessageBox.warning(self, "Doğrulama", "Sözleşme Değişikliği için önce geçerli kontrat no doğrulaması gerekir.")
            return
        sel_users = self.user.selected_users()
        if not sel_users:
            QMessageBox.warning(self, "Eksik", "Önce Kullanıcı Yönetimi ekranından kullanıcı tanımlayın.")
            return
        if not self._confirm_empty_responsible_engineer():
            return
        contract_type = self._contract_type_value()
        if self.is_sd_mode():
            sd_code = self._normalized_sd_code()
            if not sd_code:
                QMessageBox.warning(self, "Format", "SD kodu SD-1, SD-2 gibi sayısal formatta olmalı.")
                return
            self.sd_code.setText(sd_code)
            contract_type = sd_code

        signature_date = "TBD" if unknown_mode else ""
        t0_date = "TBD" if unknown_mode else ""
        t0_months = 0
        completion_date = "TBD" if unknown_mode else ""
        if not unknown_mode:
            sig = parse_iso_date(self.sig.text().strip())
            if not sig:
                QMessageBox.warning(self, "Eksik", "İmza Tarihi girin.")
                return
            t0 = parse_iso_date(self.t0.text().strip())
            if not t0:
                QMessageBox.warning(self, "Eksik", "T0 Başlangıç tarihi girin.")
                return
            t0_months = int(self.months.value())
            self.update_completion_date()
            comp = parse_iso_date(self.completion.text().strip())
            if not comp:
                QMessageBox.warning(self, "Eksik", "Termin Tarihi hesaplanamadı. T0 ve T0+Ay alanlarını kontrol edin.")
                return
            signature_date = sig.isoformat()
            t0_date = t0.isoformat()
            completion_date = comp.isoformat()

        platform_check = self.platform.currentText()
        no_check = self.no.text().strip()
        try:
            existing_contracts = self.store.list_main_contracts(platform_check)
            for ex in existing_contracts:
                ex_no = self.store._normalize_label(str(ex.get("no", "") or "").strip())
                ex_type = self.store._normalize_label(str(ex.get("type", "") or "").strip())
                if (ex_no == self.store._normalize_label(no_check) and
                        ex_type == self.store._normalize_label(contract_type)):
                    QMessageBox.warning(
                        self, "Tekrar Eden Kayıt",
                        f"'{platform_check}' platformunda '{no_check}' sözleşme numarası ve "
                        f"'{contract_type}' tipi için zaten bir kayıt mevcut.\n\n"
                        "Aynı platform + no + tip kombinasyonu kullanılamaz."
                    )
                    return
        except Exception:
            pass

        users = self.user.selected_users()
        user_display = ", ".join(users)
        self.result = ContractInfo(
            no=self.no.text().strip(),
            platform=self.platform.currentText(),
            user=user_display,
            yi_yd=self.yi_yd.text().strip() or "Yİ",
            contract_type=contract_type,
            signature_date=signature_date,
            t0_date=t0_date,
            t0_months=t0_months,
            completion_date=completion_date,
            status="Başlanmadı",
            note=self.note.text().strip(),
            acceptance_date="",
            sd_anchor_start_row=self._sd_anchor_start_row if self.is_sd_mode() else 0,
            sd_anchor_end_row=self._sd_anchor_end_row if self.is_sd_mode() else 0,
            sd_anchor_platform=self._sd_anchor_platform if self.is_sd_mode() else "",
            sd_anchor_no=self._sd_anchor_no if self.is_sd_mode() else "",
            users=users,
            platforms=self.platform.selected_platform_records(),
            platform_names=self.platform.selected_platform_names(),
            platform_ids=self.platform.selected_platform_ids(),
        )
        responsible_id = self.responsible_engineers.selected_staff_id()
        responsible_name = self.responsible_engineers._staff_name_by_id.get(responsible_id, "") if responsible_id else ""
        self.result.responsible_engineer_id = responsible_id
        self.result.responsible_engineer_name = responsible_name
        setattr(self.result, "responsible_engineer_ids", [responsible_id] if responsible_id else [])
        setattr(self.result, "responsible_engineers", [
            {"staff_id": responsible_id, "full_name": responsible_name}
        ] if responsible_id else [])
        self.accept()


