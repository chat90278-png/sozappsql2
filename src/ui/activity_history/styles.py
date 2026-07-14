from __future__ import annotations

ACTIVITY_HISTORY_QSS = r"""
QDialog#activityHistoryDialog {
    background: #eef3f8;
    color: #122033;
}
QDialog#activityHistoryDialog QWidget {
    font-family: "Segoe UI";
}
QFrame#activityHeader,
QFrame#activityToolbar,
QFrame#activityViewBar,
QFrame#activityDetailsPanel,
QFrame#activityStatePanel,
QFrame#activityTimelineDay {
    background: #ffffff;
    border: 1px solid #d8e3ee;
    border-radius: 12px;
}
QFrame#activityHeader {
    background: #f8fbff;
}
QLabel#activityEyebrow {
    color: #1f5fe0;
    font-size: 11px;
    font-weight: 800;
}
QLabel#activityTitle {
    color: #122033;
    font-size: 24px;
    font-weight: 800;
}
QLabel#activitySubtitle,
QLabel#activityMuted,
QLabel#activityDayCount,
QLabel#activityMetaLabel {
    color: #66758a;
}
QLabel#activitySummaryValue {
    color: #122033;
    font-weight: 800;
}
QPushButton#activityTab {
    min-height: 34px;
    padding: 0 13px;
    background: #ffffff;
    border: 1px solid #d8e3ee;
    border-radius: 9px;
    color: #34455d;
    font-weight: 700;
}
QPushButton#activityTab:checked {
    background: #eaf1ff;
    border-color: #9db9f5;
    color: #164aa8;
}
QPushButton#activitySegment {
    min-height: 30px;
    padding: 0 11px;
    border: none;
    border-radius: 7px;
    color: #5d6c80;
    background: transparent;
    font-weight: 700;
}
QPushButton#activitySegment:checked {
    background: #eaf1ff;
    color: #174aa8;
}
QLineEdit#activityFilter,
QComboBox#activityFilter,
QDateEdit#activityFilter {
    min-height: 36px;
    padding: 0 9px;
    background: #ffffff;
    border: 1px solid #d8e3ee;
    border-radius: 8px;
    color: #2d3d52;
}
QLineEdit#activityFilter:focus,
QComboBox#activityFilter:focus,
QDateEdit#activityFilter:focus {
    border-color: #8cacef;
}
QPushButton#activityPrimary {
    min-height: 36px;
    padding: 0 15px;
    border: none;
    border-radius: 8px;
    background: #1f5fe0;
    color: #ffffff;
    font-weight: 800;
}
QPushButton#activitySecondary {
    min-height: 34px;
    padding: 0 12px;
    border: 1px solid #d8e3ee;
    border-radius: 8px;
    background: #ffffff;
    color: #34455d;
    font-weight: 700;
}
QPushButton#activitySecondary:hover {
    background: #f5f8fc;
}
QPushButton#activityLoadMore {
    min-height: 38px;
    border: 1px solid #b8c9e6;
    border-radius: 8px;
    background: #f4f8ff;
    color: #174aa8;
    font-weight: 800;
}
QFrame#activityTimelineCard {
    background: #ffffff;
    border: 1px solid #e8eef5;
    border-radius: 10px;
}
QFrame#activityTimelineCard:hover {
    background: #fbfdff;
    border-color: #cbdafd;
}
QFrame#activityTimelineCard[selected="true"] {
    background: #f2f7ff;
    border: 2px solid #7fa4ef;
}
QLabel#activityCardTitle {
    color: #122033;
    font-size: 13px;
    font-weight: 800;
}
QLabel#activityCardSummary {
    color: #27374c;
    font-size: 13px;
}
QLabel#activityChip {
    color: #4f6076;
    background: #f7f9fc;
    border: 1px solid #d8e3ee;
    border-radius: 9px;
    padding: 2px 7px;
    font-size: 10px;
}
QLabel#activityStatusSuccess {
    color: #147154;
    background: #edf9f4;
    border: 1px solid #c9eadc;
    border-radius: 9px;
    padding: 2px 7px;
    font-size: 10px;
    font-weight: 700;
}
QLabel#activityStatusFailed {
    color: #a13030;
    background: #fff0f0;
    border: 1px solid #efcaca;
    border-radius: 9px;
    padding: 2px 7px;
    font-size: 10px;
    font-weight: 700;
}
QLabel#activityStatusPartial {
    color: #94600c;
    background: #fff8eb;
    border: 1px solid #f0dab0;
    border-radius: 9px;
    padding: 2px 7px;
    font-size: 10px;
    font-weight: 700;
}
QLabel#activityDayTitle {
    color: #122033;
    font-size: 12px;
    font-weight: 800;
}
QTableView#activityTable {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #d8e3ee;
    border-radius: 11px;
    gridline-color: #e8eef5;
    selection-background-color: #eaf1ff;
    selection-color: #122033;
}
QTableView#activityTable::item {
    padding: 7px;
}
QHeaderView::section {
    background: #f5f8fc;
    color: #4d5d72;
    border: none;
    border-bottom: 1px solid #d8e3ee;
    padding: 8px;
    font-weight: 700;
}
QFrame#activityDetailsPanel {
    background: #ffffff;
}
QLabel#activityDetailsTitle {
    color: #122033;
    font-size: 16px;
    font-weight: 800;
}
QLabel#activitySectionTitle {
    color: #526278;
    font-size: 10px;
    font-weight: 900;
}
QTreeWidget#activityChanges,
QListWidget#activityOperationEvents,
QPlainTextEdit#activityTechnicalText {
    background: #fbfdff;
    border: 1px solid #d8e3ee;
    border-radius: 8px;
    color: #27374c;
}
QToolButton#activityTechnicalToggle {
    text-align: left;
    min-height: 30px;
    border: 1px solid #d8e3ee;
    border-radius: 7px;
    background: #f8fafc;
    color: #526278;
    font-weight: 800;
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
    font-size: 15px;
    font-weight: 800;
}
QLabel#activityError {
    color: #a13030;
}
QSplitter#activitySplitter::handle {
    background: #d8e3ee;
    width: 4px;
    height: 4px;
}
"""
