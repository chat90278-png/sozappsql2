from __future__ import annotations

ACTIVITY_HISTORY_QSS = r"""
QDialog#activityHistoryDialog {
    background: #edf2f7;
    color: #122033;
}
QDialog#activityHistoryDialog QWidget {
    font-family: "Segoe UI";
    font-size: 12px;
}
QFrame#activityHeader,
QFrame#activityViewBar,
QFrame#activityDetailsPanel,
QFrame#activityStatePanel,
QFrame#activityTimelineDay {
    background: #ffffff;
    border: 1px solid #d9e3ee;
    border-radius: 10px;
}
QFrame#activityHeader {
    background: #f8fbff;
}
QFrame#activityToolbar {
    background: #f8fbff;
    border: 1px solid #cdddec;
    border-radius: 12px;
}
QLabel#activityEyebrow {
    color: #1f5fe0;
    font-size: 10px;
    font-weight: 800;
}
QLabel#activityTitle {
    color: #10213a;
    font-size: 21px;
    font-weight: 800;
}
QLabel#activitySubtitle,
QLabel#activityMuted,
QLabel#activityDayCount,
QLabel#activityMetaLabel {
    color: #66758a;
}
QLabel#activitySubtitle {
    font-size: 11px;
}
QLabel#activitySummaryValue {
    color: #122033;
    font-size: 12px;
    font-weight: 800;
}

QPushButton#activityTab {
    min-height: 29px;
    padding: 0 11px;
    background: #ffffff;
    border: 1px solid #d8e3ee;
    border-radius: 8px;
    color: #34455d;
    font-weight: 700;
}
QPushButton#activityTab:hover {
    background: #f5f8fc;
    border-color: #bdcce0;
}
QPushButton#activityTab:checked {
    background: #eaf1ff;
    border-color: #8eacf0;
    color: #164aa8;
}
QPushButton#activitySegment {
    min-height: 27px;
    padding: 0 10px;
    border: none;
    border-radius: 7px;
    color: #5d6c80;
    background: transparent;
    font-weight: 700;
}
QPushButton#activitySegment:hover {
    background: #f3f6fa;
}
QPushButton#activitySegment:checked {
    background: #eaf1ff;
    color: #174aa8;
}

QLineEdit#activityFilter,
QComboBox#activityFilter,
QDateEdit#activityFilter {
    min-height: 34px;
    padding: 0 10px;
    background: #ffffff;
    border: 1px solid #d3dfeb;
    border-radius: 9px;
    color: #24364c;
    selection-background-color: #dce8ff;
    selection-color: #122033;
}
QComboBox#activityFilter,
QDateEdit#activityFilter {
    padding-right: 36px;
}
QLineEdit#activityFilter:hover,
QComboBox#activityFilter:hover,
QDateEdit#activityFilter:hover {
    border-color: #9fb7d0;
    background: #ffffff;
}
QLineEdit#activityFilter:focus,
QComboBox#activityFilter:focus,
QDateEdit#activityFilter:focus {
    border: 2px solid #5d86df;
    background: #ffffff;
    padding-left: 9px;
}
QComboBox#activityFilter::drop-down,
QDateEdit#activityFilter::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border: none;
    border-left: 1px solid #e3eaf2;
    border-top-right-radius: 9px;
    border-bottom-right-radius: 9px;
    background: #f7faff;
}
QComboBox#activityFilter::drop-down:hover,
QDateEdit#activityFilter::drop-down:hover {
    background: #edf4ff;
}
QComboBox#activityFilter QAbstractItemView {
    background: #ffffff;
    color: #24364c;
    border: 1px solid #cbd9e8;
    border-radius: 9px;
    padding: 4px;
    outline: 0;
    selection-background-color: #e9f1ff;
    selection-color: #164aa8;
}
QComboBox#activityFilter QAbstractItemView::item {
    min-height: 28px;
    padding: 3px 8px;
    border-radius: 6px;
}
QComboBox#activityFilter QAbstractItemView::item:hover {
    background: #f2f6fc;
}
QCalendarWidget {
    background: #ffffff;
    color: #24364c;
}
QCalendarWidget QToolButton {
    color: #24364c;
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 5px 8px;
    font-weight: 700;
}
QCalendarWidget QToolButton:hover {
    background: #edf4ff;
    color: #174aa8;
}
QCalendarWidget QAbstractItemView {
    background: #ffffff;
    selection-background-color: #1f5fe0;
    selection-color: #ffffff;
    outline: none;
}

QPushButton#activityPrimary {
    min-height: 34px;
    padding: 0 13px;
    border: none;
    border-radius: 9px;
    background: #1f5fe0;
    color: #ffffff;
    font-weight: 800;
}
QPushButton#activityPrimary:hover {
    background: #174fc1;
}
QPushButton#activityPrimary:pressed {
    background: #123f9c;
}
QPushButton#activityPrimary:disabled {
    background: #a9b9d5;
    color: #edf2fa;
}
QPushButton#activitySecondary {
    min-height: 32px;
    padding: 0 11px;
    border: 1px solid #d3dfeb;
    border-radius: 9px;
    background: #ffffff;
    color: #34455d;
    font-weight: 700;
}
QPushButton#activitySecondary:hover {
    background: #edf4ff;
    border-color: #9fb7d0;
    color: #174aa8;
}
QPushButton#activityLoadMore {
    min-height: 32px;
    border: 1px solid #b8c9e6;
    border-radius: 7px;
    background: #f4f8ff;
    color: #174aa8;
    font-weight: 800;
}
QPushButton#activityLoadMore:hover {
    background: #eaf1ff;
    border-color: #91ace0;
}

QFrame#activityTimelineCard {
    background: #ffffff;
    border: 1px solid #e2e9f2;
    border-radius: 8px;
}
QFrame#activityTimelineCard:hover {
    background: #f8fbff;
    border-color: #b9ccef;
}
QFrame#activityTimelineCard:focus {
    border: 2px solid #91ace0;
}
QFrame#activityTimelineCard[selected="true"] {
    background: #edf4ff;
    border: 2px solid #6f95e3;
}
QLabel#activityCardTitle {
    color: #122033;
    font-size: 12px;
    font-weight: 800;
}
QLabel#activityCardActor {
    color: #4f6076;
    font-size: 10px;
    font-weight: 700;
}
QLabel#activityCardTime {
    color: #718096;
    font-size: 10px;
    font-weight: 700;
}
QLabel#activityCardSummary {
    color: #27374c;
    font-size: 11px;
}
QLabel#activityChip {
    color: #506176;
    background: #f6f8fb;
    border: 1px solid #d8e3ee;
    border-radius: 8px;
    padding: 1px 6px;
    font-size: 9px;
}
QLabel#activityStatusSuccess {
    color: #126448;
    background: #eaf7f1;
    border: 1px solid #bfe2d2;
    border-radius: 8px;
    padding: 1px 6px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#activityStatusFailed {
    color: #982c2c;
    background: #fff0f0;
    border: 1px solid #e8c0c0;
    border-radius: 8px;
    padding: 1px 6px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#activityStatusPartial {
    color: #855508;
    background: #fff7e7;
    border: 1px solid #ead39f;
    border-radius: 8px;
    padding: 1px 6px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#activityDayTitle {
    color: #122033;
    font-size: 11px;
    font-weight: 800;
}

QTableView#activityTable {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #d8e3ee;
    border-radius: 9px;
    gridline-color: #e8eef5;
    selection-background-color: #e7f0ff;
    selection-color: #122033;
    outline: none;
}
QTableView#activityTable::item {
    padding: 5px 7px;
    border-bottom: 1px solid #edf1f5;
}
QTableView#activityTable::item:hover {
    background: #f3f7fd;
}
QTableView#activityTable::item:selected {
    background: #e3edff;
    color: #122033;
}
QHeaderView::section {
    background: #f4f7fb;
    color: #4d5d72;
    border: none;
    border-bottom: 1px solid #d8e3ee;
    padding: 6px 7px;
    font-weight: 700;
}

QFrame#activityDetailsPanel,
QFrame#activityDetailsPanel QWidget,
QFrame#activityDetailsPanel QScrollArea,
QFrame#activityDetailsPanel QScrollArea QWidget {
    background: #ffffff;
}
QFrame#activityDetailsPanel {
    border-color: #d9e3ee;
}
QLabel#activityDetailsTitle {
    color: #122033;
    font-size: 15px;
    font-weight: 800;
}
QLabel#activityDetailRecordTitle {
    color: #122033;
    font-size: 13px;
    font-weight: 800;
    padding-top: 2px;
}
QLabel#activityDetailSummary {
    color: #27374c;
    font-size: 11px;
}
QLabel#activityDetailMeta {
    color: #52657c;
    background: transparent;
    border: none;
    border-left: 3px solid #78a0ef;
    border-radius: 0;
    padding: 3px 0 3px 8px;
    font-size: 10px;
}
QLabel#activitySectionTitle {
    color: #2758ae;
    font-size: 9px;
    font-weight: 900;
    border-bottom: 1px solid #e6edf6;
    padding-bottom: 4px;
}
QFrame#activityDetailsPanel QTreeWidget#activityChanges,
QFrame#activityDetailsPanel QListWidget#activityOperationEvents,
QFrame#activityDetailsPanel QPlainTextEdit#activityTechnicalText {
    background: #ffffff;
    alternate-background-color: #ffffff;
    border: 1px solid #e1e9f2;
    border-radius: 8px;
    color: #27374c;
    outline: none;
}
QFrame#activityDetailsPanel QHeaderView::section {
    background: #ffffff;
    color: #52657c;
    border: none;
    border-bottom: 1px solid #e6edf6;
    padding: 6px 7px;
    font-weight: 800;
}
QTreeWidget#activityChanges::item,
QListWidget#activityOperationEvents::item {
    padding: 5px 6px;
    border-bottom: 1px solid #f0f3f7;
}
QTreeWidget#activityChanges::item:hover,
QListWidget#activityOperationEvents::item:hover {
    background: #f7faff;
}
QTreeWidget#activityChanges::item:selected,
QListWidget#activityOperationEvents::item:selected {
    background: #e9f1ff;
    color: #122033;
}
QToolButton#activityTechnicalToggle {
    text-align: left;
    min-height: 29px;
    border: 1px solid #e1e9f2;
    border-radius: 8px;
    background: #ffffff;
    color: #526278;
    font-weight: 800;
    padding-left: 7px;
}
QToolButton#activityTechnicalToggle:hover {
    background: #f7faff;
    border-color: #b8cbe0;
    color: #174aa8;
}

QScrollArea#activityTimelineScroll {
    background: transparent;
    border: none;
}
QWidget#activityTimelineContent {
    background: transparent;
}
QLabel#activityStateTitle {
    color: #122033;
    font-size: 14px;
    font-weight: 800;
}
QLabel#activityError {
    color: #a13030;
}
QSplitter#activitySplitter {
    min-width: 860px;
}
QSplitter#activitySplitter::handle {
    background: #d4dfea;
    width: 3px;
    height: 3px;
}
QSplitter#activitySplitter::handle:hover {
    background: #9fb3ca;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 1px;
}
QScrollBar::handle:vertical {
    background: #c4cfdb;
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #aab9c9;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: none;
    height: 0;
}
"""
