from __future__ import annotations

"""
Runtime compatibility shims for the KY-STS desktop app.

Python imports this module automatically when the project root is on sys.path
(for example when running ``python app.py``). Keep this file deliberately small:
it should only contain safe, no-op-on-failure compatibility fixes that need to
be active before the PySide UI modules are imported.
"""


def _install_pyside6_table_enum_aliases() -> None:
    """Restore legacy table-selection enum aliases on strict PySide6 builds.

    Some migrated UI helpers call ``table.SelectRows`` and
    ``table.SingleSelection``. Depending on the PySide6 version, those values may
    only be exposed as ``QAbstractItemView.SelectionBehavior.SelectRows`` and
    ``QAbstractItemView.SelectionMode.SingleSelection``. Adding the aliases on
    Qt classes keeps the old helper code working without changing behavior on
    versions where the aliases already exist.
    """
    try:
        from PySide6.QtWidgets import QAbstractItemView, QTableWidget
    except Exception:
        return

    try:
        select_rows = getattr(QAbstractItemView, "SelectRows", None)
        if select_rows is None:
            select_rows = QAbstractItemView.SelectionBehavior.SelectRows

        single_selection = getattr(QAbstractItemView, "SingleSelection", None)
        if single_selection is None:
            single_selection = QAbstractItemView.SelectionMode.SingleSelection
    except Exception:
        return

    for cls in (QAbstractItemView, QTableWidget):
        try:
            if not hasattr(cls, "SelectRows"):
                setattr(cls, "SelectRows", select_rows)
            if not hasattr(cls, "SingleSelection"):
                setattr(cls, "SingleSelection", single_selection)
        except Exception:
            pass


_install_pyside6_table_enum_aliases()
