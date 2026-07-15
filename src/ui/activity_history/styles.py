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
QFrame#activityToolbar,
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
    min-height: 31px;
    padding: 0 8px;
    background: #ffffff;
    border: 1px solid #d8e3ee;
    border-radius: 7px;
    color: #2d3d52;
    selection-background-color: #dce8ff;
}
QLineEdit#activityFilter:hover,
QComboBox#activityFilter:hover,
QDateEdit#activityFilter:hover {
    border-color: #b8c8dc;
}
QLineEdit#activityFilter:focus,
QComboBox#activityFilter:focus,
QDateEdit#activityFilter:focus {
    border: 2px solid #7f9fdf;
    padding-left: 7px;
}
QPushButton#activityPrimary {
    min-height: 31px;
    padding: 0 13px;
    border: none;
    border-radius: 7px;
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
    min-height: 29px;
    padding: 0 11px;
    border: 1px solid #d8e3ee;
    border-radius: 7px;
    background: #ffffff;
    color: #34455d;
    font-weight: 700;
}
QPushButton#activitySecondary:hover {
    background: #f5f8fc;
    border-color: #bccbdd;
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
QLabel#activityCardSummary {
    color: #27374c;
    font-size: 12px;
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
QFrame#activityDetailsPanel {
    background: #ffffff;
}
QLabel#activityDetailsTitle {
    color: #122033;
    font-size: 15px;
    font-weight: 800;
}
QLabel#activitySectionTitle {
    color: #526278;
    font-size: 9px;
    font-weight: 900;
}
QTreeWidget#activityChanges,
QListWidget#activityOperationEvents,
QPlainTextEdit#activityTechnicalText {
    background: #fbfdff;
    border: 1px solid #d8e3ee;
    border-radius: 7px;
    color: #27374c;
    outline: none;
}
QTreeWidget#activityChanges::item,
QListWidget#activityOperationEvents::item {
    padding: 4px 5px;
}
QTreeWidget#activityChanges::item:selected,
QListWidget#activityOperationEvents::item:selected {
    background: #e7f0ff;
    color: #122033;
}
QToolButton#activityTechnicalToggle {
    text-align: left;
    min-height: 27px;
    border: 1px solid #d8e3ee;
    border-radius: 7px;
    background: #f8fafc;
    color: #526278;
    font-weight: 800;
}
QToolButton#activityTechnicalToggle:hover {
    background: #f1f5fa;
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
