from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from src.domain.share_merge_resolution import resolve_merge_plan
from src.services.share_merge_apply_service import RemoteDocumentHashMismatchError, apply_resolved_share_merge, preflight_resolved_share_merge
from src.services.share_merge_service import prepare_share_merge_plan
from src.services.sts_store import STSStore
from tests.test_share_merge_end_to_end import _edit_note, make_registered_share


def _rename_reopen_delete(path: Path) -> None:
    renamed = path.with_name(path.stem + "__renamed" + path.suffix)
    path.rename(renamed)
    conn = sqlite3.connect(str(renamed))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0].lower() == "ok"
    finally:
        conn.close()
    renamed.rename(path)
    tmp = path.with_suffix(path.suffix + ".delete-check")
    path.rename(tmp)
    tmp.unlink()


def test_share_file_handle_prepare_preflight_apply_success_paths(tmp_path):
    source, share, _ci, _cid, _metadata = make_registered_share(tmp_path)
    _edit_note(share, "REMOTE")
    plan = prepare_share_merge_plan(source, share.path)
    resolved = resolve_merge_plan(plan)
    preflight_resolved_share_merge(source, share.path, resolved)
    apply_resolved_share_merge(source, share.path, resolved)
    share_path = Path(share.path)
    source_path = Path(source.path)
    source.db.close(); share.db.close()
    _rename_reopen_delete(share_path)
    reopened = STSStore(source_path)
    try:
        assert reopened.db.conn.execute("PRAGMA integrity_check").fetchone()[0].lower() == "ok"
    finally:
        reopened.db.close()


def test_share_file_handle_failure_paths_release_share_file(tmp_path):
    source, share, ci, cid, _metadata = make_registered_share(tmp_path)
    p = tmp_path / "remote.txt"; p.write_bytes(b"remote bytes")
    share.add_contract_file("AKINCI", ci.no, p, ci.contract_type)
    resolved = resolve_merge_plan(prepare_share_merge_plan(source, share.path))
    share.db.conn.execute("UPDATE contract_files SET content_blob=?", (b"tampered",)); share.db.conn.commit()
    with pytest.raises(RemoteDocumentHashMismatchError):
        apply_resolved_share_merge(source, share.path, resolved)
    share_path = Path(share.path)
    source.db.close(); share.db.close()
    _rename_reopen_delete(share_path)
