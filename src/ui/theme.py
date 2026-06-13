# -*- coding: utf-8 -*-
STYLE = """QWidget {
    background:#e8eef5;
    font-family:'Segoe UI', Arial;
    font-size:13px;
    color:#0f172a;
}
QFrame#topbar {
    background:#263341;
    border-radius:10px;
    padding:8px;
}
QLabel#appTitle {
    color:white;
    font-weight:900;
    font-size:15px;
    background:transparent;
    padding:8px 12px;
}

QLabel#appLogo {
    background:#0f2b61;
    border:1px solid #5fb7ff;
    border-radius:12px;
    padding:3px;
}
QLabel#okPill {
    color:#047857;
    background:#dcfce7;
    border-radius:9px;
    padding:8px 14px;
    font-weight:800;
}
QLabel#okPill[status="bad"] {
    color:#b91c1c;
    background:#fee2e2;
}
QLabel#okPill[status="loading"] {
    color:#92400e;
    background:#fef3c7;
}
QLabel#miniProgressPill {
    background:#eef2f6;
    border:1px solid #c6d4e6;
    border-radius:8px;
    color:#3f5f86;
    font-weight:800;
    font-size:11px;
    padding:4px 8px;
}
QToolButton#topMenuBtn {
    background:#1f5be3;
    color:#ffffff;
    border:none;
    border-radius:8px;
    padding:6px 14px;
    min-width:44px;
    font-weight:900;
    font-size:18px;
}
QToolButton#topMenuBtn:hover {
    background:#174bc4;
}
QToolButton#topMenuBtn::menu-indicator {
    image:none;
    width:0;
}
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
QMenu#topActionsMenu::item:selected {
    background:#eef2f6;
}
QMenu#topActionsMenu::separator {
    height:1px;
    background:#d8e2ed;
    margin:4px 6px;
}
QFrame#alertStrip {
    background:#ffffff;
    border:1px solid #d8e2ed;
    border-radius:12px;
}
QFrame#todayBadge {
    background:#002060;
    border-radius:10px;
}
QLabel#todayDay {
    background:transparent;
    color:#ffffff;
    font-size:34px;
    font-weight:900;
}
QLabel#todayInfo {
    background:transparent;
    color:#d7e3ff;
    font-size:10px;
    font-weight:800;
    letter-spacing:.4px;
}
QFrame#stripDivider {
    min-width:1px;
    max-width:1px;
    background:#d8e2ed;
}
QFrame#alertGroup {
    background:#f8fbff;
    border:1px solid #d8e2ed;
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
    font-size:34px;
    font-weight:900;
}
QLabel#alertCountAmber {
    background:transparent;
    color:#b45309;
    font-size:34px;
    font-weight:900;
}
QLabel#alertLabel {
    background:transparent;
    color:#64748b;
    font-size:11px;
    font-weight:700;
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
QPushButton {
    background:#1f5be3;
    color:white;
    border:none;
    border-radius:7px;
    padding:9px 14px;
    font-weight:800;
}
QPushButton:hover { background:#174bc4; }
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
QPushButton#dateBtn {
    background:white;
    color:#334155;
    border:1px solid #d8e2ed;
    border-radius:6px;
    padding:0px;
    font-weight:700;
}
QPushButton#dateBtn:hover {
    background:#f8fbff;
    border-color:#b9c8dc;
}
QDialog#calendarPopup {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:8px;
}
QFrame#panel, QFrame#statCard, QFrame#contentPanel {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:12px;
}
QFrame#contentPanel { padding:0; }
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
QLabel#queryTitle {
    background:transparent;
    font-weight:900;
    font-size:18px;
    color:#0f172a;
    padding:0 4px 0 4px;
}
QLabel#logoWatermark {
    background:transparent;
    border:none;
    border-radius:0px;
    padding:0px;
}
QTableWidget#contractTable {
    background: #ffffff;
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
QLabel#muted {
    color:#64748b;
    background:transparent;
}
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
QTableWidget#systemCompTable {
    background:#ffffff;
    border:1px solid #d8e2ed;
    border-radius:8px;
    gridline-color:#eef2f6;
    alternate-background-color:#ffffff;
}
QTableWidget#systemCompTable::item {
    padding:5px 8px;
    border-bottom:1px solid #eef2f6;
}
QTableWidget#systemCompTable QCheckBox {
    background:transparent;
}

QLabel#sectionTitle {
    color: #1e3a5f;
    background: #e2ecf9;
    font-weight: 900;
    font-size: 12px;
    padding: 5px 12px;
    border-radius: 5px;
    letter-spacing: .3px;
    qproperty-alignment: AlignVCenter;
}
QFrame#detailContext {
    background:#f0f5fc;
    border:1px solid #c9d7ea;
    border-radius:8px;
}
QFrame#tagPanel {
    background:#f4f8fd;
    border:1px solid #d8e2ed;
    border-radius:8px;
}
QLabel#ctxMain {
    background:transparent;
    color:#1e3a5f;
    font-weight:900;
    font-size:13px;
}
QLabel#ctxPill {
    background:#e2ecf9;
    color:#35557d;
    border:1px solid #c1d3ea;
    border-radius:10px;
    padding:4px 10px;
    font-weight:800;
}
QLabel#componentName { background:transparent; font-weight:600; }
QLabel#qtyRemain { background:transparent; color:#047857; font-weight:900; }
QLabel#detailTitle { background:transparent; font-weight:900; font-size:14px; }
QPushButton#tagChipBtn {
    border-radius:13px;
    padding:4px 10px;
    font-weight:800;
}
QPushButton#colorDotBtn {
    padding:0px;
}
QLabel#tagName {
    background:transparent;
    color:#0f172a;
    font-weight:900;
    font-size:14px;
}
QLabel#tagCount {
    background:transparent;
    color:#7b8fae;
    font-weight:700;
    font-size:12px;
}
QLabel#tagDot {
    background:transparent;
    font-size:18px;
    font-weight:900;
}
QLabel#tagStateOn {
    background:#d9f3e3;
    color:#166534;
    border-radius:10px;
    padding:2px 10px;
    font-weight:800;
}
QLabel#tagStateOff {
    background:#e8edf5;
    color:#64748b;
    border-radius:10px;
    padding:2px 10px;
    font-weight:800;
}
QListWidget#tagList {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:8px;
}
QListWidget#tagList::item {
    border:none;
    padding:0px;
    margin:0px;
}
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
QListWidget, QTableWidget {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:8px;
    alternate-background-color:#f8fbff;
    gridline-color:#d8e2ed;
    selection-background-color:#dcecff;
    selection-color:#0f172a;
}
QListWidget#systemList {
    background: #ffffff;
    border: 1px solid #d8e2ed;
    border-radius: 10px;
    padding: 6px;
    outline: 0;
}

QListWidget#systemList::item {
    background: #ffffff;
    border: 1px solid #cbdff4;
    border-radius: 13px;
    margin: 5px 2px;
    padding: 0px;
    min-height: 48px;
    color: #0f172a;
}

QListWidget#systemList::item:hover {
    background: #f4f8ff;
    border: 1px solid #7db4ff;
}

QListWidget#systemList::item:selected {
    background: #0b2f6b;
    border: 1px solid #061f49;
    color: #ffffff;
}

QListWidget#systemList::item:selected:hover {
    background: #123f86;
    border: 1px solid #061f49;
}

QFrame#systemListCard {
    background: transparent;
    border: none;
}

QLabel#systemItemName {
    background: transparent;
    color: #0f172a;
    font-weight: 900;
    font-size: 12px;
}

QListWidget#systemList::item:selected QLabel#systemItemName {
    color: #ffffff;
}

QFrame#systemMetricCard {
    background:#e7f0fb;
    border:1px solid #d3e2f4;
    border-radius:7px;
}

QLabel#systemMetricTitle {
    background:transparent;
    color:#31527b;
    font-size:10px;
    font-weight:900;
}

QLabel#systemMetricValue {
    background:transparent;
    color:#0f172a;
    font-size:12px;
    font-weight:900;
}

QLabel#systemStatusPill {
    border-radius: 11px;
    padding: 2px 10px;
    font-size: 9px;
    font-weight: 900;
    color: #ffffff;
    min-width: 108px;
}

QLabel#systemStatusPill[kind="done"] {
    background: #22c55e;
}

QLabel#systemStatusPill[kind="progress"] {
    background: #f59e0b;
}

QLabel#systemStatusPill[kind="notstarted"] {
    background: #fb7185;
}

QLabel#systemItemDate {
    background: transparent;
    color: #64748b;
    font-size: 10px;
    font-weight: 800;
}

QListWidget#systemList::item:selected QLabel#systemItemDate {
    color: #dbeafe;
}

QTableWidget::item { padding:6px; }
QTableWidget::item:selected {
    color:#0f172a;
    background:#cfe0f7;
}
QTableWidget QLineEdit {
    background:#ffffff;
    color:#0f172a;
    selection-color:#0f172a;
    selection-background-color:#dcecff;
    min-height:30px;
    font-size:14px;
    padding:4px 8px;
}
QHeaderView::section {
    background:#eef2f6;
    color:#536b8e;
    padding:10px 8px;
    border:1px solid #d8e2ed;
    font-weight:900;
    font-size:12px;
}
QLabel#windowBar {
    background:#263341;
    color:white;
    padding:14px 18px;
    font-weight:900;
    border-radius:8px;
    font-size:14px;
}
QFrame#contractHeader {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #06152a, stop:0.48 #0b2747, stop:1 #07162a);
    border:0;
    border-bottom:1px solid #6aa7ff;
    border-radius:0;
}
QWidget#contractHeaderInfoRow,
QWidget#contractHeaderActions,
QWidget#metaCell {
    background:transparent;
}
QLabel#metaHeaderLabel {
    color:#8fb7df;
    font-size:9px;
    font-weight:800;
    letter-spacing:0.8px;
    background:transparent;
}
QLabel#metaHeaderValue {
    color:#f5fbff;
    font-size:13px;
    font-weight:900;
    background:transparent;
}
QFrame#metaHeaderDiv {
    background:rgba(126,170,214,76);
    min-width:1px;
    max-width:1px;
}
QWidget#headerStatusWrap,
QWidget#user {
    background:transparent;
}
QLabel#headerStatusDot {
    background:#35e790;
    border:1px solid rgba(151,255,205,0.75);
    border-radius:5px;
}
QPushButton#headerEditBtn {
    background:rgba(11,28,52,0.68);
    color:#edf6ff;
    border:1px solid rgba(115,164,217,0.48);
    border-radius:8px;
    padding:5px 15px;
    font-size:12px;
    font-weight:900;
}
QPushButton#headerEditBtn:hover {
    background:rgba(28,74,127,0.82);
    border-color:rgba(137,194,255,0.86);
}
QFrame#contractHeader QPushButton#danger {
    background:#fffaf2;
    color:#dc2626;
    border:1px solid rgba(248,113,113,0.62);
    border-radius:8px;
    padding:5px 15px;
    font-size:12px;
    font-weight:900;
}
QFrame#contractHeader QPushButton#danger:hover {
    background:#fff1f2;
    border-color:#ef4444;
}

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
QListWidget#sdList::item:hover {
    background:#1d3552;
    color:#ffffff;
}
QListWidget#sdList::item:selected {
    background:#1f5be3;
    color:#ffffff;
}
QFrame#contractVersionBar QPushButton {
    background:#123c2f;
    color:#bff7d7;
    border:1px dashed #22c55e;
    border-radius:8px;
    padding:6px 0px;
    font-size:18px;
    font-weight:900;
}
QFrame#contractVersionBar QPushButton:hover {
    background:#14532d;
}
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
    background:#e8eef5;
}
QTableWidget#qtyTable {
    background:white;
    border:1px solid #d8e2ed;
    border-radius:10px;
    gridline-color:#d8e2ed;
    selection-background-color:#f8fbff;
}
QTableWidget#qtyTable::item {
    padding:4px 6px;
}
QTableWidget#qtyTable QLineEdit {
    margin:0px;
    padding:2px 6px;
    min-height:20px;
    max-height:22px;
    font-size:12px;
    color:#0f172a;
    border:1px solid #d8e2ed;
    border-radius:4px;
    background:#ffffff;
}
QTableWidget#qtyTable QLineEdit:focus {
    border:1px solid #1f5be3;
}
QFrame#calendarSidebar {
    background:#ffffff;
    border-right:1px solid #d8e2ed;
}
QLabel#calendarSection {
    background:transparent;
    color:#64748b;
    font-size:10px;
    font-weight:900;
    letter-spacing:1px;
}
QFrame#calendarStatCard {
    background:#f0f4fc;
    border:1px solid #d8e2ed;
    border-radius:10px;
}
QLabel#calendarStatNum {
    font-size:32px;
    font-weight:900;
    color:#1f5be3;
    background:transparent;
}
QLabel#calendarStatLbl {
    font-size:10px;
    color:#64748b;
    background:transparent;
    font-weight:700;
}
QFrame#eventCardOverdue {
    background:#fef2f2;
    border:1px solid #fecaca;
    border-radius:10px;
}
QFrame#eventCardWarn {
    background:#fffbeb;
    border:1px solid #fde68a;
    border-radius:10px;
}
QLabel#eventCardNo { background:transparent; font-size:12px; font-weight:900; color:#0f172a; }
QLabel#eventCardSub { background:transparent; font-size:10px; color:#64748b; font-weight:700; }
QLabel#eventCardDate { background:transparent; font-size:10px; color:#475569; font-weight:700; }
QFrame#calendarMain {
    background:#f0f4fc;
}
QFrame#calendarTopbar {
    background:#0a1628;
    border-bottom:1px solid #111c30;
}
QLabel#calendarTopTitle {
    color:#ffffff;
    background:transparent;
    font-size:16px;
    font-weight:900;
}
QLabel#calendarTopSub {
    color:#8ea3c0;
    background:transparent;
    font-size:11px;
    font-weight:600;
}
QLabel#pillRed, QLabel#pillAmber, QLabel#pillBlue {
    border-radius:14px;
    padding:5px 12px;
    font-size:12px;
    font-weight:800;
}
QLabel#pillRed { background:#fef2f2; color:#dc2626; }
QLabel#pillAmber { background:#fffbeb; color:#d97706; }
QLabel#pillBlue { background:#e8f0fe; color:#1f5be3; }
QComboBox#calendarPlatformFilter {
    background:#ffffff;
    color:#0f172a;
    border:1px solid #334155;
    border-radius:12px;
    padding:5px 10px;
    font-size:11px;
    font-weight:800;
}
QComboBox#calendarPlatformFilter::drop-down {
    border:0px;
    width:22px;
}
QFrame#calendarModeSwitch {
    background:#3f352f;
    border:1px solid #5d4b42;
    border-radius:18px;
}
QPushButton#calendarModeButton {
    background:transparent;
    color:#a99f98;
    border:0px;
    border-radius:14px;
    padding:5px 18px;
    font-size:11px;
    font-weight:900;
}
QPushButton#calendarModeButton:checked {
    background:#d97706;
    color:#ffffff;
}
QPushButton#calendarModeButton:hover {
    color:#ffffff;
}
QFrame#calendarNav {
    background:#ffffff;
    border-bottom:1px solid #d8e2ed;
}
QLabel#calendarMonth {
    background:transparent;
    color:#0f172a;
    font-size:34px;
    font-weight:900;
}
QFrame#calendarDaysRow {
    background:#f0f4fc;
}
QLabel#calendarDayHeader {
    background:transparent;
    color:#64748b;
    font-size:11px;
    font-weight:900;
    letter-spacing:.6px;
}
QFrame#calendarCell, QFrame#calendarCellToday, QFrame#calendarCellEmpty {
    border-radius:10px;
    border:1px solid #d8e2ed;
    min-height:110px;
}
QFrame#calendarCell, QFrame#calendarCellToday { background:#ffffff; }
QFrame#calendarCellEmpty { background:transparent; border:1px solid transparent; }
QFrame#calendarCellToday { border:2px solid #1f5be3; }
QLabel#calendarCellDay {
    background:transparent;
    color:#0f172a;
    font-size:13px;
    font-weight:900;
}
QLabel#todayPill {
    background:#e8f0fe;
    color:#1f5be3;
    border-radius:8px;
    padding:2px 6px;
    font-size:9px;
    font-weight:900;
}
QLabel#calendarMore {
    background:transparent;
    color:#64748b;
    font-size:10px;
    font-weight:800;
}
QPushButton#calendarMoreButton {
    background:#f8fafc;
    color:#475569;
    border:1px dashed #cbd5e1;
    border-radius:8px;
    padding:3px 8px;
    font-size:10px;
    font-weight:900;
    text-align:left;
}
QPushButton#calendarMoreButton:hover {
    background:#e8f0fe;
    color:#1f5be3;
    border-color:#93c5fd;
}
QFrame#calendarMorePopup {
    background:#ffffff;
    border:1px solid #cbd5e1;
    border-radius:12px;
}
QLabel#calendarPopupArrow {
    background:transparent;
    color:#ffffff;
    font-size:10px;
    margin-top:-7px;
}
QLabel#calendarPopupTitle {
    background:transparent;
    color:#0f172a;
    font-size:11px;
    font-weight:900;
}
QFrame#calendarFooter {
    background:#ffffff;
    border-top:1px solid #d8e2ed;
}
QLabel#legendRed { background:transparent; color:#dc2626; font-size:11px; }
QLabel#legendAmber { background:transparent; color:#d97706; font-size:11px; }
QLabel#legendBlue { background:transparent; color:#1f5be3; font-size:11px; }
QLabel#legendGreen { background:transparent; color:#059669; font-size:11px; }
QLabel#calendarFooterNote { background:transparent; color:#64748b; font-size:11px; }"""
