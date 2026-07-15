"""Native Qt widgets used by the Activity History dialog."""

from . import styles as _styles

# The title is intentionally self-explanatory; keep the header compact by removing
# the legacy explanatory subtitle from the rendered surface.
_styles.ACTIVITY_HISTORY_QSS += r"""
QLabel#activitySubtitle {
    min-height: 0;
    max-height: 0;
    margin: 0;
    padding: 0;
    border: none;
    color: transparent;
    font-size: 0;
}
"""

from .widgets import ActivityDetailsPanel, ActivityHistoryTableModel, ActivityTimelineView

__all__ = ["ActivityDetailsPanel", "ActivityHistoryTableModel", "ActivityTimelineView"]
