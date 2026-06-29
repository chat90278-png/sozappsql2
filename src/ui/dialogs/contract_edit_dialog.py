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

class ContractEditDialog(StyledDialog):
    """Mevcut sözleşmenin ANA BİLGİLERİNİ güncelleme ekranı.

    - Sözleşme No düzenlenebilir; Platform ve Sözleşme Tipi salt okunur.
    - Diğer temel alanlar düzenlenebilir; sistemler ve teslimatlar değişmez.
    - Güncellemede platform + sözleşme tipi + sözleşme no kombinasyonu tekil kalır.
    """

    def __init__(
        self,
        store: ExcelStore,
        ci: ContractInfo,
        parent=None,
        title_text: str = "Ana Bilgileri Düzenle",
        save_text: str = "Güncelle",
        info_text: Optional[str] = None,
    ):
        super().__init__(title_text, parent)
        self.store = store
        self.ci = ci
        self.title_text = title_text
        self.save_text = save_text
        self.info_text = info_text
        self.external_events_provider = getattr(parent, "date_picker_events", None)
        self.user_records = self.store.load_users()
        self.user_to_yi_yd = {u.get("name", ""): u.get("yi_yd", "Yİ") for u in self.user_records}
        self.staff_records = self.store.list_staff_for_engineer_selection() if hasattr(self.store, "list_staff_for_engineer_selection") else []
        self.result: Optional[ContractInfo] = None
        self._default_size = QSize(820, 660)
        self.build()
        self._resize_to_safe_default()

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(10)

        title = QLabel(self.title_text)
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        info = QLabel(
            self.info_text or
            "Yalnızca sözleşmenin temel bilgileri güncellenir. "
            "Sistemler ve teslimatlar değişmez."
        )
        info.setObjectName("muted")
        info.setWordWrap(True)
        root.addWidget(info)

        self._form_scroll = QScrollArea(self)
        self._form_scroll.setFrameShape(QFrame.NoFrame)
        self._form_scroll.setWidgetResizable(True)
        self._form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._form_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._form_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._form_scroll.setStyleSheet("QScrollArea{background:transparent;border:0;} QScrollArea > QWidget > QWidget{background:transparent;}")
        self._form_container = QWidget(self._form_scroll)
        self._form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form = QVBoxLayout(self._form_container)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        self._form_scroll.setWidget(self._form_container)
        root.addWidget(self._form_scroll, 1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def readonly(text: str) -> QLineEdit:
            w = QLineEdit(str(text or ""))
            w.setReadOnly(True)
            w.setStyleSheet("background:#f1f5f9; color:#64748B; border:1px solid #e2e8f0;")
            return w

        # ── Salt okunur alanlar ──────────────────────────────────────
        ctype_text = str(self.ci.contract_type or "").strip()
        self._is_sd_contract = bool(
            re.match(r"^SD-\d+$", ctype_text.upper()) or
            self.store._normalize_label(ctype_text) == self.store._normalize_label("Sözleşme Değişikliği")
        )
        self._no_lbl       = QLineEdit(str(self.ci.no or ""))
        self._locked_platforms = self._initial_platforms()
        self._platform_select = MultiPlatformSelectWidget(self)
        self._platform_select.set_platforms(self.store.load_platforms() if hasattr(self.store, "load_platforms") else self.store.platform_names())
        self._platform_select.set_selected_platforms(self._locked_platforms)
        self._platform_select.set_locked_platforms(self._locked_platforms)
        self._platform_help = QLabel("Kayıtlı platformlar çıkarılamaz; yalnızca yeni platform eklenebilir.")
        self._platform_help.setObjectName("muted")
        self._platform_help.setWordWrap(True)
        self._platform_box = QWidget(self)
        self._platform_box.setStyleSheet("QWidget{background:transparent;border:0;}")
        platform_box_lay = QVBoxLayout(self._platform_box)
        platform_box_lay.setContentsMargins(0, 0, 0, 0)
        platform_box_lay.setSpacing(3)
        platform_box_lay.addWidget(self._platform_select)
        platform_box_lay.addWidget(self._platform_help)
        self._type_lbl     = readonly(self.ci.contract_type)
        self._type_lbl.setPlaceholderText("Örn: SD-1")
        if self._is_sd_contract:
            self._no_lbl.setReadOnly(True)
            self._no_lbl.setStyleSheet("background:#f1f5f9; color:#64748B; border:1px solid #e2e8f0;")
            self._type_lbl.setReadOnly(False)
            self._type_lbl.setEnabled(True)
            self._type_lbl.setStyleSheet("")
            self._type_lbl.editingFinished.connect(self._normalize_sd_code_field)
            self._type_lbl.textChanged.connect(self._check_duplicate_contract_key)
            no_warn_text = ""
        else:
            no_warn_text = "Aynı platform + sözleşme tipi + sözleşme no kombinasyonu kullanılamaz."
            self._no_lbl.textChanged.connect(self._check_duplicate_contract_key)
        self._no_dup_warn = QLabel(no_warn_text)
        self._no_dup_warn.setObjectName("warning")
        self._no_dup_warn.setWordWrap(True)
        self._no_dup_warn.setVisible(False)

        # ── Düzenlenebilir alanlar ────────────────────────────────────
        self.user = MultiUserSelectWidget(self)
        self.user.set_available_users([u.get("name", "") for u in self.user_records])
        init_users = list(getattr(self.ci, "users", []) or [])
        if not init_users and str(self.ci.user or "").strip():
            init_users = [x.strip() for x in str(self.ci.user or "").split(",") if x.strip()]
        self.user.set_users(init_users)

        self.yi_yd = QLineEdit()
        self.yi_yd.setReadOnly(True)
        self.yi_yd.setText(str(self.ci.yi_yd or "Yİ"))

        self.responsible_engineers = MultiStaffSelectWidget(self)
        self.responsible_engineers.set_staff_options(self.staff_records)
        responsible_ids = [int(getattr(self.ci, "responsible_engineer_id", 0) or 0)]
        if not responsible_ids[0]:
            responsible_ids = [int(x.get("staff_id") or x.get("id") or 0) for x in list(getattr(self.ci, "responsible_engineers", []) or []) if int(x.get("staff_id") or x.get("id") or 0)]
        if not responsible_ids:
            responsible_ids = [int(x or 0) for x in list(getattr(self.ci, "responsible_engineer_ids", []) or []) if int(x or 0)]
        self.responsible_engineers.set_selected_staff_ids(responsible_ids[:1])

        self.note = QLineEdit()
        self.note.setPlaceholderText("Not")
        self.note.setText(str(self.ci.note or ""))

        self.user.changed.connect(self.update_user_yi_yd)
        self.user.changed.connect(self._on_dynamic_field_changed)
        self._platform_select.currentTextChanged.connect(lambda _text: self._on_dynamic_field_changed())
        self.responsible_engineers.changed.connect(self._on_dynamic_field_changed)
        self.update_user_yi_yd()

        def add_field(label: str, widget, row: int, col: int):
            grid.addWidget(form_label(label), row * 2, col)
            grid.addWidget(widget, row * 2 + 1, col)

        add_field("Sözleşme No", self._no_lbl, 0, 0)
        add_field("Platform", self._platform_box, 0, 1)
        add_field("Sözleşmenin Sahibi Kullanıcı", self.user, 1, 0)
        add_field("Sorumlu Mühendis", self.responsible_engineers, 1, 1)
        add_field("Sözleşme Tipi", self._type_lbl, 2, 0)
        form.addLayout(grid)

        form.addWidget(form_label("Not"))
        form.addWidget(self.note)
        form.addWidget(self._no_dup_warn)
        form.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save_btn = QPushButton(self.save_text)
        save_btn.setDefault(True)
        save_btn.setAutoDefault(True)
        save_btn.clicked.connect(self.save)
        self._save_btn = save_btn
        btn_row.addWidget(cancel)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    def _on_dynamic_field_changed(self):
        for widget_name in ("_form_container", "_form_scroll", "user", "_platform_select", "responsible_engineers"):
            widget = getattr(self, widget_name, None)
            if isinstance(widget, QWidget):
                widget.updateGeometry()
        layout = getattr(self, "_form_container", None).layout() if hasattr(self, "_form_container") else None
        if layout is not None:
            layout.invalidate()
        QTimer.singleShot(0, self._resize_to_safe_default)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if isinstance(self.focusWidget(), QTextEdit):
                super().keyPressEvent(event)
                return
            self.save()
            return
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def fill_unknown_contract_no(self, *_args):
        if hasattr(self, "unknown_no_btn") and self.unknown_no_btn.isCheckable() and not self.unknown_no_btn.isChecked():
            try:
                current_no = self.no.text().strip()
                if re.search(r"\s-\s*TBD\s-\s*\d+\s*$", current_no, re.IGNORECASE):
                    self.no.clear()
            except Exception:
                pass
            if hasattr(self, "_refresh_unknown_contract_button_style"):
                self._refresh_unknown_contract_button_style()
            return
        platform = self.platform.currentText().strip()
        if not platform:
            self.no_dup_warn.setText("Geçici sözleşme numarası oluşturmak için önce platform seçin.")
            self.no_dup_warn.setVisible(True)
            return
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
        self.no_dup_warn.setVisible(False)

    def _resize_to_safe_default(self):
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        hint = self.minimumSizeHint()
        size_hint = self.sizeHint()
        target = QSize(
            max(self._default_size.width(), hint.width(), size_hint.width()),
            max(self._default_size.height(), hint.height(), size_hint.height()),
        )
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry().size()
            target.setWidth(min(target.width(), max(720, available.width() - 80)))
            target.setHeight(min(target.height(), max(560, available.height() - 100)))
        self.resize(target)

    def _initial_platforms(self) -> List[str]:
        raw = list(getattr(self.ci, "platforms", []) or [])
        if not raw and str(self.ci.platform or "").strip():
            raw = [str(self.ci.platform or "").strip()]
        out: List[str] = []
        seen = set()
        for item in raw:
            n = str(item.get("platform_name") or item.get("name") or "").strip() if isinstance(item, dict) else str(item or "").strip()
            key = n.casefold()
            if n and key not in seen:
                seen.add(key)
                out.append(n)
        return out

    def _selected_platforms(self) -> List[str]:
        vals = self._platform_select.selected_platforms() if hasattr(self, "_platform_select") else []
        out: List[str] = []
        seen = set()
        for name in vals:
            n = str(name or "").strip()
            key = n.casefold()
            if n and key not in seen:
                seen.add(key)
                out.append(n)
        return out

    def _removed_locked_platforms(self) -> List[str]:
        selected_keys = {p.casefold() for p in self._selected_platforms()}
        return [p for p in self._locked_platforms if p.casefold() not in selected_keys]

    def update_user_yi_yd(self):
        selected = (self.user.selected_users() or [""])[0].strip()
        yi_yd = self.user_to_yi_yd.get(selected, "Yİ")
        self.yi_yd.setText("YD" if str(yi_yd).upper() == "YD" else "Yİ")


    def _recalc(self):
        return

    def date_picker_events(self) -> List[dict]:
        if callable(self.external_events_provider):
            try:
                return list(self.external_events_provider() or [])
            except Exception:
                return []
        return []

    def _normalized_sd_code(self) -> str:
        raw = str(self._type_lbl.text() or "").strip().upper().replace(" ", "")
        if not raw:
            return ""
        m = re.match(r"^SD[-_]?(\d+)$", raw)
        if m:
            return f"SD-{int(m.group(1))}"
        return ""

    def _normalize_sd_code_field(self):
        if not self._is_sd_contract:
            return
        sd_code = self._normalized_sd_code()
        if sd_code:
            self._type_lbl.setText(sd_code)

    def _current_contract_type_text(self) -> str:
        if self._is_sd_contract:
            return self._normalized_sd_code() or self._type_lbl.text().strip()
        return str(self.ci.contract_type or "").strip()

    def _check_duplicate_contract_key(self) -> bool:
        """Başka bir kayıtta aynı platform + tip + no varsa uyarı gösterir."""
        no_text = self._no_lbl.text().strip()
        platform = str(self.ci.platform or "").strip()
        contract_type = self._current_contract_type_text()
        if not no_text or not platform or not contract_type:
            self._no_dup_warn.setVisible(self._is_sd_contract)
            if not self._is_sd_contract:
                self._no_lbl.setStyleSheet("")
            return False

        norm_no = self.store._normalize_label(no_text)
        norm_type = self.store._normalize_label(contract_type)
        current_row = int(getattr(self.ci, "entry_start_row", 0) or 0)
        try:
            existing_contracts = self.store.list_main_contracts(platform)
        except Exception:
            existing_contracts = []

        def mark_duplicate(message: str) -> bool:
            self._no_dup_warn.setText(message)
            self._no_dup_warn.setVisible(True)
            if not self._is_sd_contract:
                self._no_lbl.setStyleSheet(
                    "QLineEdit{border:1.5px solid #dc2626; background:#fff5f5;}"
                )
            return True

        for ex in existing_contracts:
            ex_row = int(ex.get("row") or 0)
            if current_row > 0 and ex_row == current_row:
                continue
            ex_no = self.store._normalize_label(str(ex.get("no", "") or "").strip())
            ex_type = self.store._normalize_label(str(ex.get("type", "") or "").strip())
            if ex_no == norm_no and ex_type == norm_type:
                return mark_duplicate(
                    f"⚠ '{platform}' platformunda '{contract_type}' tipi için "
                    f"'{no_text}' sözleşme numarası zaten mevcut. "
                    "Aynı platform + tip + no kombinasyonu kullanılamaz."
                )

        # Ana sözleşme no değişirken aynı no'ya bağlı SD kayıtları da taşınacak.
        # Bu yüzden taşınacak her SD tipi için hedef no altında çakışma var mı önceden kontrol edilir.
        old_no = str(self.ci.no or "").strip()
        if (not self._is_sd_contract and
                self.store._normalize_label(contract_type) == self.store._normalize_label("Ana Sözleşme") and
                self.store._normalize_label(old_no) != norm_no):
            linked_sd_rows = set()
            linked_sd_types = []
            for ex in existing_contracts:
                ex_type_raw = str(ex.get("type", "") or "").strip()
                is_sd_type = bool(
                    re.match(r"^SD-\d+$", ex_type_raw.upper()) or
                    self.store._normalize_label(ex_type_raw) == self.store._normalize_label("Sözleşme Değişikliği")
                )
                if not is_sd_type:
                    continue
                if self.store._normalize_label(str(ex.get("no", "") or "").strip()) != self.store._normalize_label(old_no):
                    continue
                linked_sd_rows.add(int(ex.get("row") or 0))
                linked_sd_types.append(ex_type_raw)
            for sd_type in linked_sd_types:
                norm_sd_type = self.store._normalize_label(sd_type)
                for ex in existing_contracts:
                    if int(ex.get("row") or 0) in linked_sd_rows:
                        continue
                    ex_no = self.store._normalize_label(str(ex.get("no", "") or "").strip())
                    ex_type = self.store._normalize_label(str(ex.get("type", "") or "").strip())
                    if ex_no == norm_no and ex_type == norm_sd_type:
                        return mark_duplicate(
                            f"⚠ Ana sözleşme no güncellenirse bağlı '{sd_type}' kaydı da "
                            f"'{no_text}' no'ya taşınacak; ancak bu platformda aynı no ve SD tipi zaten var."
                        )

        self._no_dup_warn.setVisible(False)
        if not self._is_sd_contract:
            self._no_lbl.setStyleSheet("")
        return False

    def _confirm_empty_responsible_engineer(self) -> bool:
        return True

    def save(self):
        new_no_text = self._no_lbl.text().strip()
        if not new_no_text:
            QMessageBox.warning(self, "Zorunlu Alan", "Sözleşme No girilmelidir.")
            return
        removed_platforms = self._removed_locked_platforms()
        if removed_platforms:
            QMessageBox.warning(
                self,
                "Platform çıkarılamaz",
                "Kayıt yazıldıktan sonra mevcut platform çıkarılamaz. "
                "Sadece yeni platform ekleyebilirsiniz. Çıkarılan: " + ", ".join(removed_platforms)
            )
            self._platform_select.set_selected_platforms(self._locked_platforms + [p for p in self._selected_platforms() if p.casefold() not in {x.casefold() for x in self._locked_platforms}])
            return
        selected_platforms = self._selected_platforms()
        if not selected_platforms:
            QMessageBox.warning(self, "Zorunlu Alan", "Lütfen en az bir platform seçiniz.")
            return
        if self._check_duplicate_contract_key():
            QMessageBox.warning(
                self,
                "Tekrar Eden Kayıt",
                "Aynı platform, sözleşme tipi ve sözleşme no ile başka bir kayıt bulundu. "
                "Lütfen farklı bir sözleşme no girin."
            )
            return
        norm_no = self.store._normalize_label(new_no_text)
        norm_type = self.store._normalize_label(self._current_contract_type_text())
        locked_keys = {p.casefold() for p in self._locked_platforms}
        for platform_name in selected_platforms:
            if platform_name.casefold() in locked_keys:
                continue
            try:
                candidates = self.store.list_main_contracts(platform_name)
            except Exception:
                candidates = []
            for ex in candidates:
                if (self.store._normalize_label(str(ex.get("no", "") or "")) == norm_no and
                        self.store._normalize_label(str(ex.get("type", "") or "")) == norm_type):
                    QMessageBox.warning(
                        self,
                        "Tekrar Eden Kayıt",
                        f"'{platform_name}' platformunda aynı sözleşme no ve tip zaten var. "
                        "Bu platform eklenemez."
                    )
                    return
        contract_type = str(self.ci.contract_type or "").strip()
        if self._is_sd_contract:
            sd_code = self._normalized_sd_code()
            if not sd_code:
                QMessageBox.warning(self, "Format", "SD kodu SD-1, SD-2 gibi sayısal formatta olmalı.")
                return
            self._type_lbl.setText(sd_code)
            contract_type = sd_code
        new_ci = copy.copy(self.ci)
        new_ci.no              = new_no_text
        new_ci.contract_type   = contract_type
        selected_users = self.user.selected_users()
        if not selected_users:
            QMessageBox.warning(self, "Zorunlu Alan", "En az bir kullanıcı seçmelisiniz.")
            return
        if not self._confirm_empty_responsible_engineer():
            return
        new_ci.users           = selected_users
        new_ci.user            = ", ".join(selected_users)
        new_ci.yi_yd           = self.yi_yd.text().strip() or "Yİ"
        if is_tbd_contract_no(new_no_text) or is_tbd_contract_no(getattr(self.ci, "no", "")):
            new_ci.signature_date = "TBD"
            new_ci.t0_date = "TBD"
            new_ci.t0_months = 0
            new_ci.completion_date = "TBD"
        else:
            new_ci.signature_date  = str(getattr(self.ci, "signature_date", "") or "")
            new_ci.t0_date         = str(getattr(self.ci, "t0_date", "") or "")
            new_ci.t0_months       = int(getattr(self.ci, "t0_months", 0) or 0)
            new_ci.completion_date = str(getattr(self.ci, "completion_date", "") or "")
        new_ci.status          = str(self.ci.status or "Başlanmadı")
        new_ci.note            = self.note.text().strip()
        selected_platform_ids = self._platform_select.selected_platform_ids() if hasattr(self._platform_select, "selected_platform_ids") else []
        if not selected_platform_ids:
            for name in selected_platforms:
                pid = self.store.get_platform_id(name, create=False)
                if pid is not None:
                    selected_platform_ids.append(int(pid))
        setattr(new_ci, "platforms", [{"platform_id": pid, "platform_name": name} for pid, name in zip(selected_platform_ids, selected_platforms)])
        setattr(new_ci, "platform_names", selected_platforms)
        setattr(new_ci, "platform_ids", selected_platform_ids)
        responsible_id = self.responsible_engineers.selected_staff_id()
        responsible_name = self.responsible_engineers._staff_name_by_id.get(responsible_id, "") if responsible_id else ""
        new_ci.responsible_engineer_id = responsible_id
        new_ci.responsible_engineer_name = responsible_name
        setattr(new_ci, "responsible_engineer_ids", [responsible_id] if responsible_id else [])
        setattr(new_ci, "responsible_engineers", [
            {"staff_id": responsible_id, "full_name": responsible_name}
        ] if responsible_id else [])
        self.result = new_ci
        self.accept()




