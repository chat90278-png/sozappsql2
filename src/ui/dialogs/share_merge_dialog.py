from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.models.share_models import SharePackageMetadata
from src.models.share_merge_models import MergePlan
from src.models.share_merge_apply_models import ShareMergeApplyResult
from src.models.share_merge_resolution_models import MergeDecisionKind, ResolvedMergePlan
from src.ui.presenters.share_merge_error_presenter import present_share_merge_error
from src.ui.presenters.share_merge_presenter import (
    ShareMergeDecisionController,
    decision_label,
    grouped_presented_items,
    plan_summary_text,
)
from src.ui.theme import STYLE

_log = logging.getLogger(__name__)


class ShareMergeDialog(QDialog):
    def __init__(
        self,
        *,
        merge_plan: MergePlan,
        share_path: Path | str,
        metadata: SharePackageMetadata | None,
        preflight_callback: Callable[[ResolvedMergePlan, bool], Any],
        apply_callback: Callable[[ResolvedMergePlan, bool], ShareMergeApplyResult],
        success_callback: Callable[[ShareMergeApplyResult], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.merge_plan = merge_plan
        self.share_path = Path(share_path)
        self.metadata = metadata
        self._preflight_callback = preflight_callback
        self._apply_callback = apply_callback
        self._success_callback = success_callback
        self.controller = ShareMergeDecisionController(merge_plan)
        self._decision_combos: dict[str, QComboBox] = {}
        self._submitting = False
        self.apply_result: ShareMergeApplyResult | None = None

        self.setWindowTitle("Paylaşım Değişikliklerini Birleştir")
        self.setObjectName("shareMergeDialog")
        self.setModal(True)
        self.resize(980, 740)
        self.setStyleSheet(STYLE + self._dialog_style())
        self._build()
        self._refresh_summary()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("Paylaşım Değişikliklerini Birleştir")
        title.setObjectName("shareMergeTitle")
        root.addWidget(title)

        summary = QFrame()
        summary.setObjectName("shareMergeSummary")
        grid = QGridLayout(summary)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        meta = self.metadata
        plan_counts = plan_summary_text(self.merge_plan)
        rows = [
            ("Sözleşme", getattr(meta, "source_contract_no", "") or self.merge_plan.contract_merge_uid[:8]),
            ("Paylaşım Dosyası", self.share_path.name),
            ("Oluşturulma", getattr(meta, "created_at", "") or "-"),
            ("Yetki", "Düzenleme" if getattr(meta, "permission_mode", "") == "edit" else "Görüntüleme"),
            ("Toplam Değişiklik", str(plan_counts["total"])),
            ("Uzak Değişiklik", str(plan_counts["remote"])),
            ("Yerel Değişiklik", str(plan_counts["local"])),
            ("Çakışma", str(plan_counts["conflict"])),
            ("Otomatik Uygulanabilir", str(plan_counts["safe_remote"])),
        ]
        for idx, (label, value) in enumerate(rows):
            cell = self._summary_cell(label, value)
            grid.addWidget(cell, idx // 3, idx % 3)
        root.addWidget(summary)

        live = QFrame()
        live.setObjectName("shareMergeLive")
        live_lay = QHBoxLayout(live)
        live_lay.setContentsMargins(12, 8, 12, 8)
        live_lay.setSpacing(10)
        self.live_apply = QLabel("")
        self.live_conflicts = QLabel("")
        self.live_skips = QLabel("")
        self.live_local = QLabel("")
        for lab in (self.live_apply, self.live_conflicts, self.live_skips, self.live_local):
            lab.setObjectName("shareMergePill")
            live_lay.addWidget(lab)
        live_lay.addStretch(1)
        root.addWidget(live)

        self.partial_warning = QLabel("Bazı değişiklikler bu birleştirmede atlanacak.")
        self.partial_warning.setObjectName("shareMergePartialWarning")
        self.partial_warning.setWordWrap(True)
        self.partial_warning.hide()
        root.addWidget(self.partial_warning)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("shareMergeListHost")
        self.items_layout = QVBoxLayout(host)
        self.items_layout.setContentsMargins(0, 0, 4, 0)
        self.items_layout.setSpacing(10)
        for group, items in grouped_presented_items(self.controller.resolved_plan.resolution_items):
            self._add_group(group, items)
        self.items_layout.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("")
        self.status_label.setObjectName("shareMergeStatus")
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)
        self.cancel_btn = QPushButton("Vazgeç")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn = QPushButton("Değişiklikleri Birleştir")
        self.apply_btn.setObjectName("shareMergeApply")
        self.apply_btn.clicked.connect(self._submit)
        footer.addWidget(self.cancel_btn)
        footer.addWidget(self.apply_btn)
        root.addLayout(footer)

    def _summary_cell(self, label: str, value: str) -> QWidget:
        cell = QFrame()
        cell.setObjectName("shareMergeSummaryCell")
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)
        l = QLabel(str(label))
        l.setObjectName("shareMergeSummaryLabel")
        v = QLabel(str(value or "-"))
        v.setObjectName("shareMergeSummaryValue")
        v.setWordWrap(True)
        lay.addWidget(l)
        lay.addWidget(v)
        return cell

    def _add_group(self, group: str, items) -> None:
        header = QLabel(group)
        header.setObjectName("shareMergeGroupTitle")
        self.items_layout.addWidget(header)
        for presented in items:
            self.items_layout.addWidget(self._item_card(presented))

    def _item_card(self, presented) -> QWidget:
        item = presented.item
        card = QFrame()
        card.setObjectName("shareMergeConflictCard" if item.is_conflict else "shareMergeItemCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel(presented.title)
        title.setObjectName("shareMergeItemTitle")
        title.setWordWrap(True)
        badge = QLabel(presented.change_label)
        badge.setObjectName("shareMergeConflictBadge" if item.is_conflict else "shareMergeChangeBadge")
        top.addWidget(title, 1)
        top.addWidget(badge, 0, Qt.AlignTop)
        lay.addLayout(top)

        if presented.subtitle:
            sub = QLabel(presented.subtitle)
            sub.setObjectName("shareMergeSubtitle")
            sub.setWordWrap(True)
            lay.addWidget(sub)

        values = QGridLayout()
        values.setHorizontalSpacing(8)
        values.setVerticalSpacing(5)
        for col, (caption, value, detail) in enumerate(
            (
                ("İlk Durum", presented.base_display, presented.base_detail),
                ("Bu STS'deki Değer", presented.local_display, presented.local_detail),
                ("Paylaşım Dosyasındaki Değer", presented.remote_display, presented.remote_detail),
            )
        ):
            cap = QLabel(caption)
            cap.setObjectName("shareMergeValueCaption")
            val = QLabel(value)
            val.setObjectName("shareMergeValue")
            val.setWordWrap(True)
            val.setToolTip(detail)
            values.addWidget(cap, 0, col)
            values.addWidget(val, 1, col)
        lay.addLayout(values)

        combo = QComboBox()
        combo.setObjectName("shareMergeDecisionCombo")
        combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if item.requires_user_decision:
            combo.addItem("Karar seçin", None)
        for allowed in item.allowed_decisions:
            combo.addItem(presented.decision_labels.get(allowed, decision_label(allowed)), allowed.value)
        if not item.requires_user_decision:
            idx = combo.findData(item.default_decision.value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(lambda _idx, target=item.target.target_id, widget=combo: self._on_decision_changed(target, widget))
        self._decision_combos[item.target.target_id] = combo
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(QLabel("Karar:"))
        row.addWidget(combo)
        lay.addLayout(row)
        return card

    def _on_decision_changed(self, target_id: str, combo: QComboBox) -> None:
        if self._submitting:
            return
        raw = combo.currentData()
        try:
            if raw is None:
                self.controller.clear_decision(target_id)
            else:
                self.controller.set_decision(target_id, MergeDecisionKind(str(raw)))
        except Exception as exc:
            _log.exception("Merge decision rejected target=%s", target_id)
            QMessageBox.warning(self, "Geçersiz karar", str(exc))
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        summary = self.controller.live_summary()
        self.live_apply.setText(f"Uygulanacak: {summary['operation_count']}")
        self.live_conflicts.setText(f"Çözülmemiş çakışma: {summary['unresolved_conflict_count']}")
        self.live_skips.setText(f"Atlanacak: {summary['skip_count']}")
        self.live_local.setText(f"Yerel korunacak: {summary['local_keep_count']}")
        unresolved = summary["unresolved_conflict_count"]
        structural = summary["structural_issue_count"]
        self.apply_btn.setEnabled(unresolved == 0 and structural == 0 and not self._submitting)
        if unresolved:
            self.apply_btn.setToolTip("Devam etmek için tüm çakışmalar hakkında karar verin.")
            self.status_label.setText("Devam etmek için tüm çakışmalar hakkında karar verin.")
        elif structural:
            self.apply_btn.setToolTip("Plan doğrulama sorunları çözülmeden devam edilemez.")
            self.status_label.setText("Plan doğrulama sorunları çözülmeden devam edilemez.")
        else:
            self.apply_btn.setToolTip("")
            self.status_label.setText("")
        self.partial_warning.setVisible(bool(self.controller.resolved_plan.is_partial and not unresolved))

    def _submit(self) -> None:
        if self._submitting:
            return
        resolved = self.controller.resolved_plan
        if not resolved.fully_resolved:
            self._refresh_summary()
            return
        allow_partial = bool(resolved.is_partial)
        try:
            self._set_busy(True, "Birleştirme ön kontrolü yapılıyor...")
            self._preflight_callback(resolved, allow_partial)
            self._set_busy(False)
            if not self._confirm_apply(resolved):
                return
            self._set_busy(True, "Değişiklikler birleştiriliyor...")
            result = self._apply_callback(resolved, allow_partial)
            self.apply_result = result
            self._set_busy(False)
            QMessageBox.information(
                self,
                "Paylaşım birleştirildi",
                "Paylaşım değişiklikleri başarıyla birleştirildi.\n\n"
                f"Uygulanan değişiklik: {result.operations_applied}\n"
                f"Atlanan değişiklik: {result.operations_skipped}",
            )
            if self._success_callback:
                self._success_callback(result)
            self.accept()
        except Exception as exc:
            self._set_busy(False)
            _log.exception("Share merge apply failed")
            presentation = present_share_merge_error(exc)
            _show_warning_with_detail(self, presentation.title, presentation.message, presentation.detail)

    def _confirm_apply(self, resolved: ResolvedMergePlan) -> bool:
        summary = self.controller.live_summary()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Değişiklikleri Birleştir")
        lines = [
            f"{summary['operation_count']} değişiklik uygulanacak.",
            f"{summary['local_keep_count']} yerel değişiklik korunacak.",
            f"{summary['skip_count']} değişiklik atlanacak.",
            "Bu işlem ana STS dosyasını güncelleyecek.",
        ]
        if resolved.is_partial:
            lines.insert(3, "Bazı değişiklikler bu birleştirmede atlanacak.")
        box.setText("\n".join(lines))
        cancel = box.addButton("Vazgeç", QMessageBox.RejectRole)
        apply = box.addButton("Değişiklikleri Birleştir", QMessageBox.AcceptRole)
        box.setDefaultButton(apply)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() == apply

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._submitting = busy
        self.cancel_btn.setEnabled(not busy)
        self.apply_btn.setEnabled(not busy and self.controller.can_apply())
        for combo in self._decision_combos.values():
            combo.setEnabled(not busy)
        self.status_label.setText(text)
        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        else:
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass
            self._refresh_summary()
        QApplication.processEvents()

    @staticmethod
    def _dialog_style() -> str:
        return """
        QLabel#shareMergeTitle{color:#0f2747;font-size:20px;font-weight:900;}
        QFrame#shareMergeSummary{background:#f8fbff;border:1px solid #c7d9ee;border-radius:10px;}
        QFrame#shareMergeSummaryCell{background:#ffffff;border:1px solid #e3edf8;border-radius:8px;}
        QDialog#shareMergeDialog QLabel#shareMergeSummaryLabel{background:transparent;border:0;color:#64748b;font-size:10px;font-weight:800;}
        QDialog#shareMergeDialog QLabel#shareMergeSummaryValue{background:transparent;border:0;color:#0f2747;font-size:12px;font-weight:800;}
        QFrame#shareMergeLive{background:#ffffff;border:1px solid #dbe7f5;border-radius:8px;}
        QLabel#shareMergePill{background:#eef6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:10px;padding:4px 10px;font-size:11px;font-weight:800;}
        QLabel#shareMergePartialWarning{background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;border-radius:8px;padding:8px 10px;font-weight:700;}
        QLabel#shareMergeGroupTitle{color:#0f2747;font-size:14px;font-weight:900;padding:6px 2px 0 2px;}
        QFrame#shareMergeItemCard{background:#ffffff;border:1px solid #dbe7f5;border-radius:8px;}
        QFrame#shareMergeConflictCard{background:#fffdf7;border:1px solid #facc15;border-radius:8px;}
        QDialog#shareMergeDialog QLabel#shareMergeItemTitle{background:transparent;border:0;color:#10233d;font-size:13px;font-weight:900;}
        QDialog#shareMergeDialog QLabel#shareMergeSubtitle{background:transparent;border:0;color:#64748b;font-size:11px;}
        QLabel#shareMergeChangeBadge{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:10px;padding:3px 8px;font-size:10px;font-weight:800;}
        QLabel#shareMergeConflictBadge{background:#fef3c7;color:#92400e;border:1px solid #facc15;border-radius:10px;padding:3px 8px;font-size:10px;font-weight:900;}
        QDialog#shareMergeDialog QLabel#shareMergeValueCaption{background:transparent;border:0;color:#64748b;font-size:10px;font-weight:800;}
        QDialog#shareMergeDialog QLabel#shareMergeValue{background:transparent;color:#0f2747;border:1px solid #e3edf8;border-radius:7px;padding:6px;font-size:11px;}
        QComboBox#shareMergeDecisionCombo{min-width:240px;min-height:30px;}
        QLabel#shareMergeStatus{color:#64748b;font-size:11px;font-weight:700;}
        QPushButton#shareMergeApply{background:#2563eb;color:#ffffff;border:0;border-radius:9px;padding:8px 16px;font-weight:900;}
        QPushButton#shareMergeApply:disabled{background:#cbd5e1;color:#64748b;}
        """


def _friendly_error(exc: Exception) -> str:
    name = exc.__class__.__name__
    text = str(exc)
    mapping = {
        "SharePackageAlreadyAppliedError": "Bu paylaşım dosyasındaki değişiklikler daha önce birleştirilmiş.",
        "ShareMergeApplyValidationError": "Birleştirme ön kontrolü başarısız oldu.",
        "MergeSourceChangedError": "Ana STS, plan hazırlandıktan sonra değişmiş. Lütfen birleştirmeyi yeniden başlatın.",
        "MergePackageChangedError": "Paylaşım dosyası, plan hazırlandıktan sonra değişmiş.",
        "RemoteDocumentNotFoundError": "Paylaşım dosyasındaki belge içeriği bulunamadı.",
        "RemoteDocumentHashMismatchError": "Paylaşım dosyasındaki belge içeriği doğrulanamadı.",
        "MergeOperationTargetNotFoundError": "Birleştirme hedeflerinden biri bulunamadı.",
        "MergeTransactionError": "Birleştirme işlemi başlatılamadı.",
    }
    return mapping.get(name, text or "Beklenmeyen bir hata oluştu.")


def _show_warning_with_detail(parent, title: str, text: str, detail: str = "") -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(str(title or "Uyarı"))
    box.setText(str(text or "İşlem tamamlanamadı."))
    if detail:
        box.setInformativeText(str(detail))
    box.addButton("Tamam", QMessageBox.AcceptRole)
    box.exec()
