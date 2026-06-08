# -*- coding: utf-8 -*-
STYLE = """
/* ═══ GLOBAL BASE ═══════════════════════════════════════════════════════ */
QWidget {
    background:#f0f4f8;
    font-family:'Segoe UI', Arial;
    font-size:13px;
    color:#0f172a;
}
QDialog, QMainWindow, QFrame#panel, QFrame#statCard, QFrame#contentPanel,
QFrame#sidebar, QWidget#detailPanel {
    background:#ffffff;
}

/* ═══ TOPBAR ════════════════════════════════════════════════════════════ */
QFrame#topbar {
    background:#0f1c2e;
    border-radius:10px;
    padding:6px 10px;
}
QLabel#appTitle {
    color:#e2e8f0;
    font-weight:900;
    font-size:13px;
    background:transparent;
    padding:6px 10px;
    letter-spacing:.04em;
}
QLabel#appLogo {
    background:#1e3a5f;
    border:1px solid #2d5fa6;
    border-radius:10px;
    padding:3px;
}
QLabel#okPill {
    color:#34d399;
    background:#0d3321;
    border:1px solid #065f46;
    border-radius:14px;
    padding:5px 14px;
    font-weight:800;
    font-size:11px;
}
QLabel#okPill[status="bad"] {
    color:#f87171;
    background:#300;
    border:1px solid #991b1b;
}
QLabel#okPill[status="loading"] {
    color:#fbbf24;
    background:#1a1200;
    border:1px solid #92400e;
}
QLabel#miniProgressPill {
    background:#1e3a5f;
    border:1px solid #2d5fa6;
    border-radius:8px;
    color:#93c5fd;
    font-weight:800;
    font-size:11px;
    padding:4px 8px;
}
QToolButton#topMenuBtn {
    background:#1e3a5f;
    color:#94a3b8;
    border:none;
    border-radius:8px;
    padding:6px 12px;
    min-width:36px;
    font-weight:900;
    font-size:18px;
}
QToolButton#topMenuBtn:hover {
    background:#2d5fa6;
    color:#e2e8f0;
}
QToolButton#topMenuBtn::menu-indicator { image:none; width:0; }
QMenu#topActionsMenu {
    background:#ffffff;
    border:1px solid #d8e2ed;
    border-radius:10px;
    padding:6px;
}
QMenu#topActionsMenu::item {
    padding:8px 14px;
    border-radius:6px;
    color:#0f172a;
    font-weight:700;
}
QMenu#topActionsMenu::item:selected { background:#eef2f6; }
QMenu#topActionsMenu::separator {
    height:1px;
    background:#d8e2ed;
    margin:4px 6px;
}

/* ═══ ALERT STRIP ═══════════════════════════════════════════════════════ */
QFrame#alertStrip {
    background:#ffffff;
    border:none;
    border-bottom:1px solid #e2eaf3;
    border-radius:0px;
}
QFrame#todayBadge {
    background:#1e40af;
    border-radius:10px;
}
QLabel#todayDay {
    background:transparent;
    color:#ffffff;
    font-size:28px;
    font-weight:900;
}
QLabel#todayInfo {
    background:transparent;
    color:#bfdbfe;
    font-size:9px;
    font-weight:800;
    letter-spacing:.5px;
}
QFrame#stripDivider {
    min-width:1px;
    max-width:1px;
    background:#e2eaf3;
}
QFrame#alertGroup {
    background:#f8fafc;
    border:1px solid #e2eaf3;
    border-radius:10px;
}
QLabel#alertIconRed {
    background:#fef2f2;
    color:#dc2626;
    border-radius:8px;
    padding:5px 7px;
    font-size:16px;
}
QLabel#alertIconAmber {
    background:#fffbeb;
    color:#b45309;
    border-radius:8px;
    padding:5px 7px;
    font-size:16px;
}
QLabel#alertCountRed {
    background:transparent;
    color:#dc2626;
    font-size:28px;
    font-weight:900;
}
QLabel#alertCountAmber {
    background:transparent;
    color:#d97706;
    font-size:28px;
    font-weight:900;
}
QLabel#alertLabel {
    background:transparent;
    color:#94a3b8;
    font-size:10px;
    font-weight:700;
    letter-spacing:.4px;
}
QLabel#upcomingLabel {
    background:transparent;
    color:#64748b;
    font-size:11px;
    font-weight:800;
}
QScrollArea#upcomingScroll {
    border:none;
    background:transparent;
}
QScrollArea#upcomingScroll QWidget {
    background:transparent;
}
QPushButton#upcomingPill {
    border-radius:8px;
    padding:6px 10px;
    font-size:12px;
    font-weight:800;
    color:#0f172a;
    border:1px solid #d8e2ed;
    background:#f8fbff;
}
QPushButton#upcomingPill[kind="red"] {
    color:#dc2626;
    background:#fef2f2;
    border:1px solid #fecaca;
}
QPushButton#upcomingPill[kind="amber"] {
    color:#b45309;
    background:#fffbeb;
    border:1px solid #fde68a;
}

/* ═══ LEFT PANEL — PLATFORMLAR ══════════════════════════════════════════ */
QFrame#panel, QFrame#statCard, QFrame#contentPanel {
    background:#ffffff;
    border:1px solid #e2eaf3;
    border-radius:12px;
}
QFrame#contentPanel { padding:0; }
QLabel#panelTitle {
    background:transparent;
    font-weight:700;
    font-size:10px;
    color:#94a3b8;
    padding:4px 2px;
    letter-spacing:.1em;
    border-radius:0px;
}
QListWidget#mainPlatformList {
    background:#ffffff;
    border:none;
    outline:0;
    padding:4px 0;
}
QListWidget#mainPlatformList::item {
    background:#ffffff;
    border-radius:0px;
    padding:0px;
    margin:0px;
}
QListWidget#mainPlatformList::item:hover {
    background:#f0f7ff;
}
QListWidget#mainPlatformList::item:selected {
    background:#eff6ff;
    border-left:3px solid #2563eb;
}
QPushButton#newContractBtn {
    background:#2563eb;
    color:#ffffff;
    border:none;
    border-radius:0px;
    border-top:1px solid #1d4ed8;
    padding:13px 14px;
    font-weight:800;
    font-size:13px;
}
QPushButton#newContractBtn:hover {
    background:#1d4ed8;
}
QPushButton#newContractBtn:active {
    background:#1e40af;
}

/* Panel içindeki widget'lar beyaz — global #f0f4f8 sızmasın */
QFrame#panel QWidget, QFrame#panel QFrame {
    background:#ffffff;
}
QFrame#panel QFrame#platformInfoBar {
    background:#f8fbff;
}
QFrame#panel QScrollArea, QFrame#panel QScrollBar {
    background:#ffffff;
}
QFrame#platformInfoBar {
    background:#f8fbff;
    border-top:1px solid #e2eaf3;
}
QFrame#platformInfoBar QLabel { color:#64748b; font-size:11px; }
QFrame#platformInfoBar QPushButton {
    background:transparent;
    border:0;
    color:#2563eb;
    font-size:11px;
    font-weight:800;
    padding:2px 4px;
}
QLabel#platformSelectionBadge {
    background:#dbeafe;
    color:#1d4ed8;
    border-radius:9px;
    padding:2px 7px;
    font-size:11px;
    font-weight:800;
}

/* ═══ RIGHT PANEL — SÖZLEŞME TABLOSU ════════════════════════════════════ */
QLabel#queryTitle {
    background:transparent;
    font-weight:900;
    font-size:15px;
    color:#0f172a;
    padding:0 4px;
}
QTableWidget#contractTable {
    background:#ffffff;
    gridline-color:#f1f5f9;
    border:none;
    border-radius:0px;
    selection-background-color:#eff6ff;
    selection-color:#1e40af;
}
QTableWidget#contractTable::item {
    padding:7px 8px;
    border-bottom:1px solid #f8fafc;
    background:#ffffff;
}
QTableWidget#contractTable::item:selected {
    background:#eff6ff;
    color:#1e40af;
}
QTableWidget#contractTable::item:alternate {
    background:#fafcff;
}
QHeaderView::section {
    background:#f8fafc;
    color:#64748b;
    font-size:11px;
    font-weight:700;
    padding:8px 8px;
    border:none;
    border-bottom:1.5px solid #e2eaf3;
    border-right:1px solid #f1f5f9;
    letter-spacing:.04em;
    text-transform:uppercase;
}
QHeaderView::section:hover {
    background:#f0f4f8;
    color:#374151;
}
QHeaderView::section:first {
    border-left:none;
}

/* ═══ BUTONLAR ══════════════════════════════════════════════════════════ */
QPushButton {
    background:#1f5be3;
    color:white;
    border:none;
    border-radius:7px;
    padding:9px 14px;
    font-weight:800;
}
QPushButton:hover { background:#174bc4; }
QPushButton:active { background:#1338a0; }
QPushButton#secondary {
    background:white;
    color:#0f172a;
    border:1px solid #d8e2ed;
}
QPushButton#secondary:hover { background:#f8fbff; border-color:#b9c8dc; }
QPushButton#danger {
    background:#fff;
    color:#dc2626;
    border:1px solid #fecaca;
}
QPushButton#danger:hover { background:#fef2f2; }
QPushButton#dateBtn {
    background:white;
    color:#334155;
    border:1px solid #d8e2ed;
    border-radius:6px;
    padding:0px;
    font-weight:700;
}
QPushButton#dateBtn:hover { background:#f8fbff; border-color:#b9c8dc; }

/* ═══ FORM ELEMANLARI ════════════════════════════════════════════════════ */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit {
    background:white;
    color:#0f172a;
    selection-color:#0f172a;
    selection-background-color:#dcecff;
    border:1px solid #d8e2ed;
    border-radius:6px;
    padding:7px;
}
QLineEdit#qtyInput {
    background:white;
    color:#0f172a;
    border:1px solid #d8e2ed;
    border-radius:6px;
    padding:7px;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width:0px; height:0px; border:none;
}
QSpinBox::up-arrow, QSpinBox::down-arrow,
QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {
    width:0px; height:0px;
}

/* ═══ DİALOG ve PANEL TİTLELARI ════════════════════════════════════════ */
QDialog#calendarPopup {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:8px;
}
QFrame#tableBox {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:10px;
    padding:8px;
}
QLabel#panelTitle, QLabel#dialogTitle {
    background:#eef2f6;
    font-weight:900;
    font-size:18px;
    padding:9px 12px;
    border-radius:4px;
}
QLabel#mainTitle {
    background:#eef2f6;
    font-weight:900;
    font-size:20px;
    padding:10px 14px;
    border-radius:4px;
}
QLabel#logoWatermark {
    background:transparent;
    border:none;
    border-radius:0px;
    padding:0px;
}
QLabel#sideTitle {
    background:#eef2f6;
    color:#0f172a;
    font-weight:900;
    padding:9px 12px;
    border-radius:4px;
}
QLabel#metaLabel, QLabel#formLabel {
    color:#536b8e;
    font-size:11px;
    font-weight:900;
    background:transparent;
    letter-spacing:.3px;
}
QLabel#metaValue {
    font-size:16px;
    font-weight:900;
    background:transparent;
    color:#020617;
}
QFrame#metaCard {
    background:#eef2f6;
    border:none;
    border-radius:4px;
}
QLabel#statValue {
    font-size:24px;
    font-weight:900;
    background:#e8eef5;
    padding:8px;
}
QLabel#muted { color:#64748b; background:transparent; }
QLabel#warning {
    color:#b45309;
    background:#fff7ed;
    padding:8px;
    border-radius:6px;
}
QLabel#systemDialogHeader {
    background:#f0f5fc;
    color:#0f172a;
    border:1px solid #d8e2ed;
    border-radius:8px;
    padding:12px 14px;
    font-size:16px;
    font-weight:900;
}
QFrame#systemFormCard {
    background:#f8fbff;
    border:1px solid #d8e2ed;
    border-radius:8px;
}
QLabel#selectionPill {
    background:#dcecff;
    color:#1f5be3;
    border-radius:10px;
    padding:3px 9px;
    font-size:11px;
    font-weight:900;
}
QLabel#sectionTitle {
    color:#1e3a5f;
    background:#e2ecf9;
    font-weight:900;
    font-size:12px;
    padding:5px 12px;
    border-radius:5px;
    letter-spacing:.3px;
    qproperty-alignment:AlignVCenter;
}

/* ═══ LİST ve TABLE GENEL ════════════════════════════════════════════════ */
QListWidget, QTableWidget {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:8px;
    alternate-background-color:#f8fbff;
    gridline-color:#d8e2ed;
    selection-background-color:#dcecff;
    selection-color:#0f172a;
}
QListWidget#tagList {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:8px;
}
QListWidget#tagList::item { border:none; padding:0px; margin:0px; }
QTableWidget::item { padding:6px; }
QTableWidget::item:selected { color:#0f172a; background:#cfe0f7; }
QTableWidget QLineEdit {
    background:#ffffff;
    color:#0f172a;
    selection-color:#0f172a;
    selection-background-color:#dcecff;
    min-height:30px;
    font-size:14px;
    padding:4px 8px;
}

/* ═══ SYSTEM LIST ════════════════════════════════════════════════════════ */
QListWidget#systemList {
    background:#ffffff;
    border:1px solid #d8e2ed;
    border-radius:10px;
    padding:6px;
    outline:0;
}
QListWidget#systemList::item {
    background:#ffffff;
    border:1px solid #cbdff4;
    border-radius:13px;
    margin:5px 2px;
    padding:0px;
    min-height:48px;
    color:#0f172a;
}
QListWidget#systemList::item:hover {
    background:#f4f8ff;
    border:1px solid #7db4ff;
}
QListWidget#systemList::item:selected {
    background:#0b2f6b;
    border:1px solid #061f49;
    color:#ffffff;
}
QListWidget#systemList::item:selected:hover {
    background:#123f86;
    border:1px solid #061f49;
}
QFrame#systemListCard { background:transparent; border:none; }
QLabel#systemItemName {
    background:transparent;
    color:#0f172a;
    font-weight:900;
    font-size:12px;
}
QListWidget#systemList::item:selected QLabel#systemItemName { color:#ffffff; }
QFrame#systemMetricCard {
    background:#e7f0fb;
    border:1px solid #d3e2f4;
    border-radius:7px;
}
QLabel#systemMetricTitle { background:transparent; color:#31527b; font-size:10px; font-weight:900; }
QLabel#systemMetricValue { background:transparent; color:#0f172a; font-size:12px; font-weight:900; }
QLabel#systemStatusPill {
    border-radius:11px;
    padding:2px 10px;
    font-size:9px;
    font-weight:900;
    color:#ffffff;
    min-width:108px;
}
QLabel#systemStatusPill[kind="done"] { background:#22c55e; }
QLabel#systemStatusPill[kind="progress"] { background:#f59e0b; }
QLabel#systemStatusPill[kind="notstarted"] { background:#fb7185; }
QLabel#systemItemDate { background:transparent; color:#64748b; font-size:10px; font-weight:800; }
QListWidget#systemList::item:selected QLabel#systemItemDate { color:#dbeafe; }

/* ═══ SD / VERSION BAR ════════════════════════════════════════════════════ */
QFrame#contractVersionBar {
    background:#102033;
    border:1px solid #0b1726;
    border-radius:10px;
}
QListWidget#sdList {
    background:transparent;
    border:none;
    color:#cfe0f7;
}
QListWidget#sdList::item {
    color:#cfe0f7;
    background:transparent;
    padding:9px 5px;
    margin:2px 0px;
    border-radius:8px;
    font-size:11px;
    font-weight:900;
    min-height:22px;
}
QListWidget#sdList::item:hover { background:#1d3552; color:#ffffff; }
QListWidget#sdList::item:selected { background:#1f5be3; color:#ffffff; }
QFrame#contractVersionBar QPushButton {
    background:#123c2f;
    color:#bff7d7;
    border:1px dashed #22c55e;
    border-radius:8px;
    padding:6px 0px;
    font-size:18px;
    font-weight:900;
}
QFrame#contractVersionBar QPushButton:hover { background:#14532d; }

/* ═══ CONTRACT HEADER ════════════════════════════════════════════════════ */
QFrame#contractHeader {
    background:#1e2e41;
    border:0;
    border-bottom:1px solid #1a2a3a;
    border-radius:0;
}
QWidget#metaCell { background:transparent; }
QLabel#metaHeaderLabel { color:#8db8d8; font-size:10px; font-weight:600; letter-spacing:0.5px; background:transparent; }
QLabel#metaHeaderValue { color:#ffffff; font-size:14px; font-weight:800; background:transparent; }
QFrame#metaHeaderDiv { background:#3a546e; min-width:1px; max-width:1px; }
QPushButton#headerEditBtn {
    background:rgba(255,255,255,0.10);
    color:#d8eaff;
    border:1px solid rgba(255,255,255,0.20);
    border-radius:8px;
    padding:5px 14px;
    font-size:13px;
    font-weight:700;
}
QPushButton#headerEditBtn:hover { background:rgba(255,255,255,0.18); border-color:rgba(255,255,255,0.35); }

/* ═══ SIDEBAR / DETAIL PANEL ════════════════════════════════════════════ */
QFrame#sidebar {
    background:#f6f9fc;
    border:1px solid #d8e2ed;
    border-radius:0px;
}
QWidget#detailPanel {
    background:#fbfdff;
    border-left:4px solid #1f5be3;
}
QScrollArea#plainScroll {
    border:1px solid #d8e2ed;
    background:#f0f4f8;
}

/* ═══ QTY TABLE ═════════════════════════════════════════════════════════ */
QTableWidget#systemCompTable {
    background:#ffffff;
    border:1px solid #d8e2ed;
    border-radius:8px;
    gridline-color:#eef2f6;
    alternate-background-color:#ffffff;
}
QTableWidget#systemCompTable::item { padding:5px 8px; border-bottom:1px solid #eef2f6; }
QTableWidget#systemCompTable QCheckBox { background:transparent; }
QTableWidget#qtyTable {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:10px;
    gridline-color:#d8e2ed;
    selection-background-color:#f8fbff;
}
QTableWidget#qtyTable::item { padding:4px 6px; }
QTableWidget#qtyTable QLineEdit {
    margin:0px; padding:2px 6px; min-height:20px; max-height:22px;
    font-size:12px; color:#0f172a; border:1px solid #d8e2ed; border-radius:4px; background:#ffffff;
}
QTableWidget#qtyTable QLineEdit:focus { border:1px solid #1f5be3; }

/* ═══ TAGS ══════════════════════════════════════════════════════════════ */
QLabel#tagName { background:transparent; color:#0f172a; font-weight:900; font-size:14px; }
QLabel#tagCount { background:transparent; color:#7b8fae; font-weight:700; font-size:12px; }
QLabel#tagDot { background:transparent; font-size:18px; font-weight:900; }
QLabel#tagStateOn { background:#d9f3e3; color:#166534; border-radius:10px; padding:2px 10px; font-weight:800; }
QLabel#tagStateOff { background:#e8edf5; color:#64748b; border-radius:10px; padding:2px 10px; font-weight:800; }
QPushButton#tagChipBtn { border-radius:13px; padding:4px 10px; font-weight:800; }
QPushButton#colorDotBtn { padding:0px; }
QLabel#componentName { background:transparent; font-weight:600; }
QLabel#qtyRemain { background:transparent; color:#047857; font-weight:900; }
QLabel#detailTitle { background:transparent; font-weight:900; font-size:14px; }

/* ═══ DETAY CONTEXT ═════════════════════════════════════════════════════ */
QFrame#detailContext { background:#f0f5fc; border:1px solid #c9d7ea; border-radius:8px; }
QFrame#tagPanel { background:#f4f8fd; border:1px solid #d8e2ed; border-radius:8px; }
QLabel#ctxMain { background:transparent; color:#1e3a5f; font-weight:900; font-size:13px; }
QLabel#ctxPill {
    background:#e2ecf9; color:#35557d; border:1px solid #c1d3ea;
    border-radius:10px; padding:4px 10px; font-weight:800;
}

/* ═══ TAKVİM ════════════════════════════════════════════════════════════ */
QFrame#calendarSidebar { background:#ffffff; border-right:1px solid #d8e2ed; }
QLabel#calendarSection { background:transparent; color:#64748b; font-size:10px; font-weight:900; letter-spacing:1px; }
QFrame#calendarStatCard { background:#f0f4fc; border:1px solid #d8e2ed; border-radius:10px; }
QLabel#calendarStatNum { font-size:32px; font-weight:900; color:#1f5be3; background:transparent; }
QLabel#calendarStatLbl { font-size:10px; color:#64748b; background:transparent; font-weight:700; }
QFrame#eventCardOverdue { background:#fef2f2; border:1px solid #fecaca; border-radius:10px; }
QFrame#eventCardWarn { background:#fffbeb; border:1px solid #fde68a; border-radius:10px; }
QLabel#eventCardNo { background:transparent; font-size:12px; font-weight:900; color:#0f172a; }
QLabel#eventCardSub { background:transparent; font-size:10px; color:#64748b; font-weight:700; }
QLabel#eventCardDate { background:transparent; font-size:10px; color:#475569; font-weight:700; }
QFrame#calendarMain { background:#f0f4fc; }
QFrame#calendarTopbar { background:#0a1628; border-bottom:1px solid #111c30; }
QLabel#calendarTopTitle { color:#ffffff; background:transparent; font-size:16px; font-weight:900; }
QLabel#calendarTopSub { color:#8ea3c0; background:transparent; font-size:11px; font-weight:600; }
QLabel#pillRed, QLabel#pillAmber, QLabel#pillBlue { border-radius:14px; padding:5px 12px; font-size:12px; font-weight:800; }
QLabel#pillRed { background:#fef2f2; color:#dc2626; }
QLabel#pillAmber { background:#fffbeb; color:#d97706; }
QLabel#pillBlue { background:#e8f0fe; color:#1f5be3; }
QComboBox#calendarPlatformFilter {
    background:#ffffff; color:#0f172a; border:1px solid #334155;
    border-radius:12px; padding:5px 10px; font-size:11px; font-weight:800;
}
QComboBox#calendarPlatformFilter::drop-down { border:0px; width:22px; }
QFrame#calendarModeSwitch { background:#3f352f; border:1px solid #5d4b42; border-radius:18px; }
QPushButton#calendarModeButton {
    background:transparent; color:#a99f98; border:0px;
    border-radius:14px; padding:5px 18px; font-size:11px; font-weight:900;
}
QPushButton#calendarModeButton:checked { background:#d97706; color:#ffffff; }
QPushButton#calendarModeButton:hover { color:#ffffff; }
QFrame#calendarNav { background:#ffffff; border-bottom:1px solid #d8e2ed; }
QLabel#calendarMonth { background:transparent; color:#0f172a; font-size:34px; font-weight:900; }
QFrame#calendarDaysRow { background:#f0f4fc; }
QLabel#calendarDayHeader { background:transparent; color:#64748b; font-size:11px; font-weight:900; letter-spacing:.6px; }
QFrame#calendarCell, QFrame#calendarCellToday, QFrame#calendarCellEmpty {
    border-radius:10px; border:1px solid #d8e2ed; min-height:110px;
}
QFrame#calendarCell, QFrame#calendarCellToday { background:#ffffff; }
QFrame#calendarCellEmpty { background:transparent; border:1px solid transparent; }
QFrame#calendarCellToday { border:2px solid #1f5be3; }
QLabel#calendarCellDay { background:transparent; color:#0f172a; font-size:13px; font-weight:900; }
QLabel#todayPill { background:#e8f0fe; color:#1f5be3; border-radius:8px; padding:2px 6px; font-size:9px; font-weight:900; }
QLabel#calendarMore { background:transparent; color:#64748b; font-size:10px; font-weight:800; }
QPushButton#calendarMoreButton {
    background:#f8fafc; color:#475569; border:1px dashed #cbd5e1;
    border-radius:8px; padding:3px 8px; font-size:10px; font-weight:900; text-align:left;
}
QPushButton#calendarMoreButton:hover { background:#e8f0fe; color:#1f5be3; border-color:#93c5fd; }
QFrame#calendarMorePopup { background:#ffffff; border:1px solid #cbd5e1; border-radius:12px; }
QLabel#calendarPopupArrow { background:transparent; color:#ffffff; font-size:10px; margin-top:-7px; }
QLabel#calendarPopupTitle { background:transparent; color:#0f172a; font-size:11px; font-weight:900; }
QFrame#calendarFooter { background:#ffffff; border-top:1px solid #d8e2ed; }
QLabel#legendRed { background:transparent; color:#dc2626; font-size:11px; }
QLabel#legendAmber { background:transparent; color:#d97706; font-size:11px; }
QLabel#legendBlue { background:transparent; color:#1f5be3; font-size:11px; }
QLabel#legendGreen { background:transparent; color:#059669; font-size:11px; }
QLabel#calendarFooterNote { background:transparent; color:#64748b; font-size:11px; }
QLabel#windowBar {
    background:#263341; color:white; padding:14px 18px;
    font-weight:900; border-radius:8px; font-size:14px;
}
"""

# ═══════════════════════════════════════════════════════════════════════
# Application bootstrap
# ═══════════════════════════════════════════════════════════════════════
import importlib.util
import sys
from pathlib import Path


SUPPORTED_DATA_SUFFIXES = {".sts", ".sqlite", ".sqlite3", ".db", ".xlsx", ".xlsm"}


def _require_qt() -> None:
    """Fail with an actionable message when the desktop dependency is absent."""
    if importlib.util.find_spec("PySide6") is None:
        raise SystemExit(
            "PySide6 bulunamadı. Uygulamayı çalıştırmak için PySide6 kurulu olmalı: "
            "python -m pip install PySide6"
        )


def _resolve_initial_path(argv: list[str]) -> Path | None:
    """Return the first supported data-file argument, if the user supplied one."""
    for raw in argv[1:]:
        candidate = Path(raw).expanduser()
        if candidate.suffix.lower() in SUPPORTED_DATA_SUFFIXES:
            return candidate
    return None


class _LazyQtMainWindowMixin:
    """Marker mixin so static imports of app.py do not require PySide6."""


class STSMainWindow(_LazyQtMainWindowMixin):
    """Lightweight STS desktop shell.

    The business logic lives under ``src/services`` and reusable dialogs under
    ``src/ui``.  This class only wires those pieces into an executable entry
    point, which is the file used by ``STS.spec``.
    """

    def __init__(self, store, data_path: Path):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QFrame,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QListWidget,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )

        self._qt = {
            "Qt": Qt,
            "QMainWindow": QMainWindow,
            "QMessageBox": QMessageBox,
            "QTableWidgetItem": QTableWidgetItem,
        }
        self._base = QMainWindow()
        self.store = store
        self.data_path = Path(data_path)
        self.active_platform = ""
        self.contract_index: list[dict] = []

        self._base.setWindowTitle(f"STS - {self.data_path.name}")
        self._base.resize(1280, 760)
        self._base.setStyleSheet(STYLE)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QHBoxLayout(topbar)
        top.setContentsMargins(12, 8, 12, 8)
        top.setSpacing(8)
        title = QLabel("KONFİGÜRASYON YÖNETİMİ SÖZLEŞME TAKİP SİSTEMİ")
        title.setObjectName("appTitle")
        self.status_label = QLabel(str(self.data_path))
        self.status_label.setObjectName("miniProgressPill")
        refresh_btn = QPushButton("Yenile")
        refresh_btn.clicked.connect(self.refresh_all)
        export_btn = QPushButton("Excel’e Aktar")
        export_btn.clicked.connect(self.open_export_dialog)
        export_btn.setEnabled(hasattr(self.store, "export_to_excel"))
        db_btn = QPushButton("Database Yönetimi")
        db_btn.clicked.connect(self.open_database_management)
        db_btn.setEnabled(bool(getattr(self.store, "supports_database_management", lambda: False)()))
        top.addWidget(title, 1)
        top.addWidget(self.status_label, 0)
        top.addWidget(refresh_btn, 0)
        top.addWidget(export_btn, 0)
        top.addWidget(db_btn, 0)
        root.addWidget(topbar)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        left_panel = QFrame()
        left_panel.setObjectName("panel")
        left_panel.setFixedWidth(280)
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(12, 12, 12, 12)
        left.addWidget(QLabel("PLATFORMLAR"))
        self.platform_list = QListWidget()
        self.platform_list.setObjectName("mainPlatformList")
        self.platform_list.currentTextChanged.connect(self.on_platform_changed)
        left.addWidget(self.platform_list, 1)
        body.addWidget(left_panel)

        right_panel = QFrame()
        right_panel.setObjectName("contentPanel")
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(12, 12, 12, 12)
        self.summary_label = QLabel("Sözleşmeler")
        self.summary_label.setObjectName("mainTitle")
        right.addWidget(self.summary_label)
        self.contract_table = QTableWidget(0, 7)
        self.contract_table.setObjectName("contractTable")
        self.contract_table.setHorizontalHeaderLabels([
            "Platform",
            "Sözleşme No",
            "Tip",
            "Kullanıcı",
            "Durum",
            "Tamamlanma",
            "Kabul",
        ])
        self.contract_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.contract_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.contract_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right.addWidget(self.contract_table, 1)
        body.addWidget(right_panel, 1)

        self._base.setCentralWidget(central)
        self.refresh_all()

    def show(self) -> None:
        self._base.show()

    def refresh_all(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidgetItem, QMessageBox

        try:
            platforms = list(self.store.platform_names())
            self.contract_index = list(self.store.build_contract_index())
        except Exception as exc:
            QMessageBox.critical(self._base, "Veri yüklenemedi", str(exc))
            return

        previous = self.active_platform
        self.platform_list.blockSignals(True)
        self.platform_list.clear()
        all_item = QListWidgetItem("Tüm Platformlar")
        all_item.setData(Qt.UserRole, "")
        self.platform_list.addItem(all_item)
        selected_row = 0
        for row, platform in enumerate(platforms, start=1):
            item = QListWidgetItem(platform)
            item.setData(Qt.UserRole, platform)
            self.platform_list.addItem(item)
            if platform == previous:
                selected_row = row
        self.platform_list.setCurrentRow(selected_row)
        self.platform_list.blockSignals(False)
        self.active_platform = previous if previous in platforms else ""
        self.populate_contracts()

    def on_platform_changed(self) -> None:
        item = self.platform_list.currentItem()
        self.active_platform = item.data(self._qt["Qt"].UserRole) if item else ""
        self.populate_contracts()

    def populate_contracts(self) -> None:
        QTableWidgetItem = self._qt["QTableWidgetItem"]
        rows = [
            row for row in self.contract_index
            if not self.active_platform or row.get("platform") == self.active_platform
        ]
        self.contract_table.setRowCount(len(rows))
        fields = ["platform", "contract_no", "contract_type", "user", "status", "completion_date", "acceptance_date"]
        for r, data in enumerate(rows):
            for c, field in enumerate(fields):
                self.contract_table.setItem(r, c, QTableWidgetItem(str(data.get(field) or "")))
        scope = self.active_platform or "Tüm Platformlar"
        self.summary_label.setText(f"{scope} - {len(rows)} sözleşme")

    def open_database_management(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        from src.ui.dialogs.database_management import DatabaseManagementDialog

        if not bool(getattr(self.store, "supports_database_management", lambda: False)()):
            QMessageBox.information(self._base, "Uygun değil", "Database yönetimi yalnızca .sts veritabanı dosyalarında kullanılabilir.")
            return
        dlg = DatabaseManagementDialog(self.store, self._base)
        dlg.exec()
        self.refresh_all()

    def open_export_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from src.ui.dialogs.excel_export_options import ExcelExportDialog

        if not hasattr(self.store, "export_to_excel"):
            QMessageBox.information(self._base, "Uygun değil", "Excel aktarımı yalnızca .sts veritabanı dosyalarında kullanılabilir.")
            return
        dlg = ExcelExportDialog(
            self.store,
            self._base,
            active_platform=self.active_platform,
            contract_index=self.contract_index,
        )
        if not dlg.exec() or not dlg.result_options:
            return
        target, _ = QFileDialog.getSaveFileName(
            self._base,
            "Excel çıktısını kaydet",
            str(self.data_path.with_suffix(".xlsx")),
            "Excel (*.xlsx)",
        )
        if not target:
            return
        try:
            self.store.export_to_excel(target, options=dlg.result_options)
        except Exception as exc:
            QMessageBox.critical(self._base, "Excel aktarımı başarısız", str(exc))
            return
        QMessageBox.information(self._base, "Excel aktarımı tamamlandı", f"Dosya oluşturuldu:\n{target}")


def _select_data_path(parent=None) -> Path | None:
    from src.ui.dialogs.workbook_start import WorkbookStartDialog

    dlg = WorkbookStartDialog(parent)
    if dlg.exec() and dlg.selected_path:
        return Path(dlg.selected_path)
    return None


def _open_store(data_path: Path):
    if data_path.suffix.lower() in {".xlsx", ".xlsm"}:
        from src.services.excel_store import ExcelStore

        return ExcelStore(data_path)
    from src.services.sts_store import STSStore

    return STSStore(data_path)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _require_qt()

    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication(argv)
    app.setApplicationName("STS")
    data_path = _resolve_initial_path(argv) or _select_data_path()
    if data_path is None:
        return 0
    try:
        store = _open_store(data_path)
    except Exception as exc:
        QMessageBox.critical(None, "Veri dosyası açılamadı", str(exc))
        return 1
    window = STSMainWindow(store, data_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
