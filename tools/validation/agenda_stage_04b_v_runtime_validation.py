from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASELINE = "55d6c6da4fae99c4074532302f7f11ce6c091623"
PRODUCT = "8088d2e65bbf7daee3ff07667e0f438b2099e96e"
TEMP_PATHS = {
    ".github/workflows/agenda-stage-04b-v-runtime-validation.yml",
    "tools/validation/agenda_stage_04b_v_runtime_validation.py",
}
NOW = datetime(2026, 7, 13, 12, 0, 0)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def dump_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def write_json(path, value):
    path.write_text(dump_text(value), encoding="utf-8")


def run(command, cwd, log_path, env=None):
    merged = os.environ.copy()
    merged.update(env or {})
    result = subprocess.run(
        command,
        cwd=cwd,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        errors="replace",
    )
    log_path.write_text(
        "$ " + subprocess.list2cmdline(command) + f"\nexit_code={result.returncode}\n\n" + result.stdout,
        encoding="utf-8",
    )
    return result


def git_output(cwd, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        errors="replace",
    )
    require(result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def sha_info(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def junit_summary(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    nodes = sorted(
        {
            f"{case.get('classname', '')}::{case.get('name', '')}"
            for case in cases
            if case.find("failure") is not None or case.find("error") is not None
        }
    )
    return {
        "tests": len(cases),
        "passed": sum(
            case.find("failure") is None
            and case.find("error") is None
            and case.find("skipped") is None
            for case in cases
        ),
        "failures": sum(case.find("failure") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
        "nodes": nodes,
        "parse_valid": True,
    }


class SourceSpy:
    def __init__(self, repository):
        self.repository = repository
        self.personal_calls = []
        self.all_calls = 0
        self.load_calls = []
        self.platform_calls = 0
        original = repository._platform_names_by_contract

        def counted_platform(ids):
            self.platform_calls += 1
            return original(ids)

        repository._platform_names_by_contract = counted_platform

    def list_personal_contract_ids(self, staff_id):
        self.personal_calls.append(staff_id)
        return self.repository.list_personal_contract_ids(staff_id)

    def list_all_contract_ids(self):
        self.all_calls += 1
        return self.repository.list_all_contract_ids()

    def load_personal_sources(self, contract_ids):
        normalized = sorted(int(value) for value in contract_ids)
        self.load_calls.append(normalized)
        return self.repository.load_personal_sources(contract_ids)


class StateSpy:
    def __init__(self, repository):
        self.repository = repository
        self.calls = defaultdict(list)

    def _delegate(self, name, *args, **kwargs):
        self.calls[name].append({"args": list(args), "kwargs": kwargs})
        return getattr(self.repository, name)(*args, **kwargs)

    def get_states(self, *args, **kwargs):
        return self._delegate("get_states", *args, **kwargs)

    def touch_presented(self, *args, **kwargs):
        return self._delegate("touch_presented", *args, **kwargs)

    def mark_seen(self, *args, **kwargs):
        return self._delegate("mark_seen", *args, **kwargs)

    def snooze(self, *args, **kwargs):
        return self._delegate("snooze", *args, **kwargs)

    def clear_snooze(self, *args, **kwargs):
        return self._delegate("clear_snooze", *args, **kwargs)


class ProviderSpy:
    def __init__(self, provider):
        self.provider = provider
        self.code = provider.code
        self.enabled_calls = 0
        self.build_calls = 0

    def is_enabled(self, context):
        self.enabled_calls += 1
        return self.provider.is_enabled(context)

    def build(self, context, sources):
        self.build_calls += 1
        return self.provider.build(context, sources)


class DisabledProvider:
    code = "disabled_validation_provider"

    def __init__(self):
        self.enabled_calls = 0
        self.build_calls = 0

    def is_enabled(self, context):
        self.enabled_calls += 1
        return False

    def build(self, context, sources):
        self.build_calls += 1
        return ()


def spy_snapshot(source_spy, state_spy, providers):
    return {
        "source": {
            "personal": list(source_spy.personal_calls),
            "all": source_spy.all_calls,
            "load": list(source_spy.load_calls),
            "platform": source_spy.platform_calls,
        },
        "state": dict(state_spy.calls),
        "providers": {
            provider.code: {
                "is_enabled": provider.enabled_calls,
                "build": provider.build_calls,
            }
            for provider in providers
        },
    }


def seed_database(db):
    from src import auth
    from src.models.share_models import SHARE_STATUS_RETURNED

    conn = db.conn
    auth.ensure_document_locks_table(conn)
    with db.tx():
        role_ids = {
            str(row["name"]): int(row["id"])
            for row in conn.execute("SELECT id,name FROM roles")
        }
        conn.execute(
            "INSERT INTO roles(name,display_name,is_system) VALUES('custom_agenda','Custom Agenda',0)"
        )
        role_ids["custom_agenda"] = int(
            conn.execute("SELECT id FROM roles WHERE name='custom_agenda'").fetchone()[0]
        )

        permission_map = {
            "personnel": {"view_contracts", "unlock_own_documents"},
            "manager": {"view_contracts", "edit_contracts", "unlock_all_documents"},
            "viewer": {"view_contracts"},
            "custom_agenda": {"view_contracts", "unlock_own_documents"},
        }
        relevant = {
            "view_contracts",
            "edit_contracts",
            "lock_documents",
            "unlock_own_documents",
            "unlock_all_documents",
        }
        for role_name, allowed in permission_map.items():
            for code in relevant:
                conn.execute(
                    """
                    INSERT INTO role_permissions(role_id,permission_code,is_allowed)
                    VALUES(?,?,?)
                    ON CONFLICT(role_id,permission_code)
                    DO UPDATE SET is_allowed=excluded.is_allowed
                    """,
                    (role_ids[role_name], code, int(code in allowed)),
                )

        staff = {}
        for key, role_name, device, full_name in (
            ("owner", "personnel", "owner-device", "Ortak Ad"),
            ("other", "personnel", "other-device", "Diğer Personel"),
            ("manager", "manager", "manager-device", "Yönetici"),
            ("viewer", "viewer", "viewer-device", "Görüntüleyici"),
            ("custom", "custom_agenda", "custom-device", "Özel Rol"),
        ):
            staff[key] = int(
                conn.execute(
                    """
                    INSERT INTO staff(device_name,full_name,password_hash,role,role_id,is_active)
                    VALUES(?,?,?,?,?,1)
                    """,
                    (device, full_name, "x", role_name, role_ids[role_name]),
                ).lastrowid
            )

        platform_id = int(
            conn.execute(
                "INSERT INTO platforms(name,display_name,is_active) VALUES('Platform V','Platform V',1)"
            ).lastrowid
        )

        contracts = {}
        contract_specs = (
            ("critical", "C-CRIT", "2026-07-12"),
            ("own", "C-OWN", "2026-08-01"),
            ("unknown", "C-TBD", "TBD"),
            ("unlocked", "C-OFF", "2026-09-01"),
            ("null_at", "C-NULAT", "2026-09-02"),
            ("outside", "C-OUT", "2026-09-03"),
            ("blank", "", "2026-09-04"),
            ("custom", "C-CUSTOM", "2026-09-05"),
        )
        for key, contract_no, completion in contract_specs:
            contracts[key] = int(
                conn.execute(
                    """
                    INSERT INTO contracts(
                        platform_id,contract_no,contract_type,status,completion_date,
                        merge_uid,revision
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        platform_id,
                        contract_no,
                        "Ana",
                        "Açık",
                        completion,
                        f"merge-{key}",
                        1,
                    ),
                ).lastrowid
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO contract_platforms(
                    contract_id,platform_id,sort_order,is_primary
                ) VALUES(?,?,0,1)
                """,
                (contracts[key], platform_id),
            )

        for contract_key in ("critical", "own", "unlocked"):
            conn.execute(
                """
                INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary)
                VALUES(?,?,1)
                """,
                (contracts[contract_key], staff["owner"]),
            )
        conn.execute(
            """
            INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary)
            VALUES(?,?,1)
            """,
            (contracts["custom"], staff["custom"]),
        )
        conn.execute(
            """
            INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary)
            VALUES(?,?,1)
            """,
            (contracts["outside"], staff["other"]),
        )

        lock_rows = (
            ("own", 1, staff["owner"], "owner-device", "Ortak Ad", "2026-07-13 08:00:00"),
            ("critical", 1, staff["other"], "owner-device", "Ortak Ad", "2026-07-13 08:05:00"),
            ("unknown", 1, None, "", "", "2026-07-13 08:10:00"),
            ("unlocked", 0, staff["owner"], "owner-device", "Ortak Ad", "2026-07-13 08:15:00"),
            ("null_at", 1, staff["owner"], "owner-device", "Ortak Ad", None),
            ("outside", 1, staff["other"], "other-device", "Diğer Personel", "2026-07-13 08:20:00"),
            ("blank", 1, None, "", "", "2026-07-13 08:25:00"),
            ("custom", 1, staff["custom"], "custom-device", "Özel Rol", "2026-07-13 08:30:00"),
        )
        for key, is_locked, owner_id, device, full_name, locked_at in lock_rows:
            conn.execute(
                """
                INSERT INTO document_locks(
                    contract_id,is_locked,locked_by_staff_id,locked_by_device_name,
                    locked_by_full_name,locked_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    contracts[key],
                    is_locked,
                    owner_id,
                    device,
                    full_name,
                    locked_at,
                    "2026-07-13 09:00:00",
                ),
            )

        conn.execute(
            """
            INSERT INTO share_packages(
                share_package_id,contract_id,contract_merge_uid,source_contract_revision,
                permission_mode,share_format_version,snapshot_format_version,
                base_snapshot_sha256,created_at,created_by_staff_id,
                created_by_full_name,exported_filename,status,last_imported_at,
                last_imported_by_staff_id,last_remote_snapshot_sha256,return_count
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "pkg-stage-04b",
                contracts["critical"],
                "merge-critical",
                1,
                "edit",
                2,
                1,
                "base-stage-04b",
                "2026-07-12 10:00:00",
                staff["owner"],
                "Ortak Ad",
                "pkg-stage-04b.sts",
                SHARE_STATUS_RETURNED,
                "2026-07-13 07:00:00",
                staff["owner"],
                "remote-stage-04b",
                1,
            ),
        )

        conn.execute(
            """
            INSERT INTO staff_agenda_state(
                staff_id,agenda_key,first_presented_at,last_presented_at,
                seen_at,seen_version,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                staff["owner"],
                "collision:seed",
                "2026-07-01",
                "2026-07-02",
                "2026-07-03",
                "V1",
                "2026-07-01",
                "2026-07-03",
            ),
        )

    db.add_log(
        "documents_locked",
        entity_type="contract",
        entity_id=contracts["unlocked"],
        entity_key=str(contracts["unlocked"]),
        message="Activity-only lock signal",
    )
    require(staff["owner"] == 1, "numeric collision precondition requires staff.id=1")
    return {"staff": staff, "contracts": contracts, "platform": platform_id}


def staff_session(db, staff_id):
    from src import auth

    row = db.conn.execute(
        """
        SELECT s.*,r.name AS role_name,r.display_name AS role_display_name
        FROM staff AS s
        LEFT JOIN roles AS r ON r.id=s.role_id
        WHERE s.id=?
        """,
        (staff_id,),
    ).fetchone()
    return auth.enrich_staff_permissions(db.conn, auth.build_current_staff(row))


def run_service(db, session, *, override=(), touch=False, include_disabled=False):
    from src.domain.agenda.providers import (
        DeadlineAgendaProvider,
        DocumentLockAgendaProvider,
        ReturnedShareAgendaProvider,
        UnknownDateAgendaProvider,
    )
    from src.services.agenda_context_factory import PersonalAgendaContextFactory
    from src.services.agenda_source_repository import AgendaSourceRepository
    from src.services.agenda_state_repository import AgendaStateRepository
    from src.services.staff_agenda_service import StaffAgendaService

    source_spy = SourceSpy(AgendaSourceRepository(db))
    state_spy = StateSpy(AgendaStateRepository(db))
    providers = [
        ProviderSpy(DeadlineAgendaProvider()),
        ProviderSpy(ReturnedShareAgendaProvider()),
        ProviderSpy(DocumentLockAgendaProvider()),
        ProviderSpy(UnknownDateAgendaProvider()),
    ]
    if include_disabled:
        providers.append(DisabledProvider())
    context = PersonalAgendaContextFactory(now_provider=lambda: NOW).build(
        session,
        now=NOW,
        personal_contract_ids=override,
    )
    result = StaffAgendaService(
        db,
        state_repository=state_spy,
        source_repository=source_spy,
        providers=providers,
    ).build(context, touch_presented=touch)
    return context, result, spy_snapshot(source_spy, state_spy, providers), state_spy


def runtime_validation(feature, evidence):
    os.chdir(feature)
    sys.path.insert(0, str(feature))

    from PySide6.QtWidgets import QApplication
    from src import auth
    from src.domain.agenda.constants import (
        AgendaContractScopeCode,
        AgendaLifecycleType,
        AgendaPresentationProfileCode,
        AgendaSeverity,
    )
    from src.domain.agenda.presentation import project_agenda_result
    from src.domain.agenda.providers import (
        DeadlineAgendaProvider,
        DocumentLockAgendaProvider,
        ReturnedShareAgendaProvider,
        UnknownDateAgendaProvider,
    )
    from src.services.agenda_context_factory import PersonalAgendaContextFactory
    from src.services.agenda_source_repository import AgendaSourceRepository
    from src.services.agenda_state_repository import AgendaStateRepository
    from src.services.personal_agenda_facade import PersonalAgendaFacade, AgendaInteractionError
    from src.services.staff_agenda_service import StaffAgendaService
    from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSDatabase
    from src.ui.agenda_compact_widget import AgendaCompactWidget
    from src.ui.agenda_detail_window import AgendaDetailWindow

    output = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        db = STSDatabase(Path(temp_dir) / "agenda-stage-04b-v.sts", source="Stage 04B-V")
        try:
            require(CURRENT_SCHEMA_VERSION == 18, "CURRENT_SCHEMA_VERSION must be 18")
            ids = seed_database(db)
            staff = ids["staff"]
            contracts = ids["contracts"]

            owner = staff_session(db, staff["owner"])
            manager = staff_session(db, staff["manager"])
            viewer = staff_session(db, staff["viewer"])
            custom = staff_session(db, staff["custom"])

            repository = AgendaSourceRepository(db)
            active_scope = [
                contracts["own"],
                contracts["critical"],
                contracts["unknown"],
                contracts["unlocked"],
                contracts["null_at"],
            ]
            sources = repository.list_document_lock_sources(active_scope)
            require(
                {source.contract_id for source in sources}
                == {contracts["own"], contracts["critical"], contracts["unknown"]},
                "active source filter mismatch",
            )
            duplicate_sources = repository.list_document_lock_sources(
                [contracts["own"], contracts["own"]]
            )
            require(len(duplicate_sources) == 1, "duplicate input produced duplicate source")
            empty_trace = []
            db.conn.set_trace_callback(empty_trace.append)
            empty = repository.list_document_lock_sources([])
            db.conn.set_trace_callback(None)
            require(empty == () and not empty_trace, "empty IDs must not query")

            trace = []
            before_changes = db.conn.total_changes
            before_tx = db.conn.in_transaction
            db.conn.set_trace_callback(trace.append)
            readonly_sources = repository.list_document_lock_sources(active_scope)
            db.conn.set_trace_callback(None)
            require(db.conn.total_changes == before_changes, "source read mutated database")
            require(db.conn.in_transaction == before_tx, "source read changed transaction state")
            require(
                trace and all(statement.lstrip().upper().startswith("SELECT") for statement in trace),
                "source trace must contain SELECT only",
            )
            require(
                contracts["unlocked"] not in {source.contract_id for source in readonly_sources},
                "activity log inferred a lock source",
            )
            require(
                [
                    (source.contract_no.casefold(), source.contract_id)
                    for source in readonly_sources
                ]
                == sorted(
                    (source.contract_no.casefold(), source.contract_id)
                    for source in readonly_sources
                ),
                "source order is not deterministic",
            )

            repo_spy = SourceSpy(AgendaSourceRepository(db))
            bundle = repo_spy.load_personal_sources(
                [contracts["critical"], contracts["own"], contracts["unknown"]]
            )
            require(repo_spy.platform_calls == 1, "shared platform lookup must run once")
            require(bundle.calendar and bundle.returned_shares and bundle.document_locks, "bundle coexistence")
            source_evidence = {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "active_contract_ids": [source.contract_id for source in sources],
                "metadata": [source.__dict__ for source in sources],
                "empty_query_count": len(empty_trace),
                "readonly": {
                    "total_changes_before": before_changes,
                    "total_changes_after": db.conn.total_changes,
                    "in_transaction_before": before_tx,
                    "in_transaction_after": db.conn.in_transaction,
                    "trace": trace,
                },
                "platform_lookup_count": repo_spy.platform_calls,
                "bundle_counts": {
                    "calendar": len(bundle.calendar),
                    "returned_shares": len(bundle.returned_shares),
                    "document_locks": len(bundle.document_locks),
                },
            }
            output["document_lock_source"] = source_evidence
            write_json(evidence / "document-lock-source-smoke.json", source_evidence)
            (evidence / "document-lock-source-smoke.log").write_text("PASS\n", encoding="utf-8")

            owner_context, owner_result, owner_calls, _ = run_service(db, owner)
            owner_lock_items = [item for item in owner_result.items if item.kind == "document_lock"]
            require(owner_context.presentation_profile.code == AgendaPresentationProfileCode.PERSONAL, "owner profile")
            require(owner_context.contract_scope == AgendaContractScopeCode.RESPONSIBLE, "owner scope")
            require([item.contract_id for item in owner_lock_items] == [contracts["own"]], "owner visibility")

            lock_only = dict(owner)
            lock_only["permissions"] = frozenset({"view_contracts", "lock_documents"})
            _, lock_only_result, lock_only_calls, _ = run_service(db, lock_only)
            require(not [item for item in lock_only_result.items if item.kind == "document_lock"], "lock-only item")
            require(lock_only_calls["providers"]["document_lock"] == {"is_enabled": 1, "build": 0}, "lock-only provider calls")

            collision = dict(owner)
            collision["permissions"] = frozenset({"view_contracts", "unlock_own_documents"})
            collision["full_name"] = "Ortak Ad"
            collision["device_name"] = "owner-device"
            _, collision_result, collision_calls, _ = run_service(
                db,
                collision,
                override={contracts["critical"]},
            )
            require(
                not [item for item in collision_result.items if item.kind == "document_lock"],
                "name/device collision counted as own",
            )

            manager_context, manager_result, manager_calls, _ = run_service(
                db,
                manager,
                include_disabled=True,
            )
            manager_locks = [item for item in manager_result.items if item.kind == "document_lock"]
            expected_manager_locks = {
                contracts["own"],
                contracts["critical"],
                contracts["unknown"],
                contracts["outside"],
                contracts["blank"],
                contracts["custom"],
            }
            require(manager_context.presentation_profile.code == AgendaPresentationProfileCode.MANAGEMENT, "manager profile")
            require({item.contract_id for item in manager_locks} == expected_manager_locks, "manager unlock-all visibility")
            require(len({item.key for item in manager_locks}) == len(manager_locks), "duplicate lock item")
            require(manager_calls["source"]["load"] and len(manager_calls["source"]["load"]) == 1, "bundle load once")
            require(manager_calls["providers"]["disabled_validation_provider"] == {"is_enabled": 1, "build": 0}, "disabled provider")

            manager_own = dict(manager)
            manager_own["permissions"] = frozenset({"view_contracts", "unlock_own_documents"})
            _, manager_own_result, _, _ = run_service(db, manager_own)
            require(
                not [item for item in manager_own_result.items if item.kind == "document_lock"],
                "manager own-only should have no owned locks",
            )

            _, viewer_result, viewer_calls, _ = run_service(db, viewer)
            require(
                not [item for item in viewer_result.items if item.kind == "document_lock"],
                "viewer lock item",
            )
            require(viewer_calls["providers"]["document_lock"] == {"is_enabled": 1, "build": 0}, "viewer provider disabled")

            custom_context, custom_result, _, _ = run_service(db, custom)
            require(custom_context.presentation_profile.code == AgendaPresentationProfileCode.PERSONAL, "custom profile")
            require(
                [item.contract_id for item in custom_result.items if item.kind == "document_lock"]
                == [contracts["custom"]],
                "custom explicit permission snapshot",
            )
            custom_none = dict(custom)
            custom_none["permissions"] = frozenset({"view_contracts"})
            _, custom_none_result, _, _ = run_service(db, custom_none)
            require(not [item for item in custom_none_result.items if item.kind == "document_lock"], "custom role synthesis")

            both = dict(manager)
            both["permissions"] = frozenset(
                {"view_contracts", "unlock_own_documents", "unlock_all_documents"}
            )
            _, both_result, _, _ = run_service(db, both)
            both_locks = [item for item in both_result.items if item.kind == "document_lock"]
            require(len(both_locks) == len({item.key for item in both_locks}), "both permissions duplicate")

            _, override_result, override_calls, _ = run_service(
                db,
                owner,
                override={contracts["critical"]},
            )
            require(
                override_calls["source"]["personal"] == []
                and override_calls["source"]["all"] == 0
                and override_calls["source"]["load"] == [[contracts["critical"]]],
                "explicit override calls",
            )
            require(
                not [item for item in override_result.items if item.kind == "document_lock"],
                "override owner filter",
            )

            no_view = dict(manager)
            no_view["permissions"] = frozenset({"unlock_all_documents"})
            _, no_view_result, no_view_calls, _ = run_service(db, no_view)
            require(no_view_result.items == (), "no-view result")
            require(
                no_view_calls["source"] == {"personal": [], "all": 0, "load": [], "platform": 0},
                "no-view source calls",
            )
            require(
                all(
                    calls == {"is_enabled": 0, "build": 0}
                    for calls in no_view_calls["providers"].values()
                ),
                "no-view provider calls",
            )
            require(not no_view_calls["state"], "no-view state calls")

            matrix = {
                "personnel_responsible_own": {
                    "contracts": [item.contract_id for item in owner_lock_items],
                    "calls": owner_calls,
                },
                "lock_only": {"lock_count": 0, "calls": lock_only_calls},
                "name_device_collision": {"lock_count": 0, "calls": collision_calls},
                "manager_unlock_all": {
                    "contracts": sorted(item.contract_id for item in manager_locks),
                    "calls": manager_calls,
                },
                "manager_own_only": {"lock_count": 0},
                "viewer": {"lock_count": 0, "calls": viewer_calls},
                "custom": {
                    "contracts": [
                        item.contract_id for item in custom_result.items if item.kind == "document_lock"
                    ]
                },
                "both_permissions": {"count": len(both_locks)},
                "explicit_override": {"calls": override_calls},
                "no_view": {"calls": no_view_calls},
            }
            output["permission_matrix"] = matrix
            write_json(evidence / "permission-profile-scope-matrix.json", matrix)
            (evidence / "permission-profile-scope-matrix.log").write_text("PASS\n", encoding="utf-8")

            provider = DocumentLockAgendaProvider()
            owner_sources = AgendaSourceRepository(db).load_personal_sources(
                [contracts["own"], contracts["critical"], contracts["unknown"], contracts["blank"]]
            )
            owner_ctx = PersonalAgendaContextFactory(now_provider=lambda: NOW).build(owner, now=NOW)
            manager_ctx = PersonalAgendaContextFactory(now_provider=lambda: NOW).build(manager, now=NOW)
            own_item = next(
                item
                for item in provider.build(owner_ctx, owner_sources)
                if item.contract_id == contracts["own"]
            )
            manager_projected = provider.build(manager_ctx, owner_sources)
            other_item = next(item for item in manager_projected if item.contract_id == contracts["critical"])
            unknown_item = next(item for item in manager_projected if item.contract_id == contracts["unknown"])
            blank_item = next(item for item in manager_projected if item.contract_id == contracts["blank"])

            for item, relation in (
                (own_item, "OWN"),
                (other_item, "OTHER"),
                (unknown_item, "UNKNOWN"),
            ):
                payload = dict(item.detail_payload)
                require(item.provider_code == "document_lock" and item.kind == "document_lock", "item provider/kind")
                require(item.key == f"document_lock:contract:{item.contract_id}", "item key")
                require(item.lifecycle_type == AgendaLifecycleType.CONDITION, "item lifecycle")
                require(item.priority == 800 and item.severity == AgendaSeverity.ATTENTION, "item priority")
                require(item.version == f"LOCKED:{item.actor_staff_id or 0}:{item.event_at}", "item version")
                require(item.event_at == item.effective_date, "item timestamps")
                require(item.reason_code == "DOCUMENT_LOCKED", "item reason code")
                require(item.reason_text == ("OWN_LOCK" if relation == "OWN" else "OTHER_LOCK"), "item reason text")
                require(item.supports_snooze is True, "item snooze")
                require(item.action_hints == ("open_contract",), "item action hints")
                require(payload["source_type"] == "document_lock", "payload source")
                require(payload["owner_relation"] == relation, "payload owner relation")
                require("unlock_document" not in item.action_hints and "lock_document" not in item.action_hints, "direct action")
            require(own_item.description == "Belgeler sizin tarafınızdan kilitlendi.", "own description")
            require(other_item.description == "Belgeler Ortak Ad tarafından kilitlendi.", "other description")
            require(unknown_item.description == "Belgeler başka bir personel tarafından kilitlendi.", "unknown description")
            require(blank_item.title == "Sözleşme belgeleri kilitli", "blank contract title")
            item_contract = {
                "own": own_item,
                "other": other_item,
                "unknown": unknown_item,
                "blank": blank_item,
            }
            output["item_contract"] = item_contract
            write_json(evidence / "item-contract-smoke.json", item_contract)
            (evidence / "item-contract-smoke.log").write_text("PASS\n", encoding="utf-8")

            kinds = [item.kind for item in manager_result.items]
            require("deadline" in kinds and "returned_share" in kinds and "document_lock" in kinds and "unknown_date" in kinds, "coexistence kinds")
            critical_index = next(i for i, item in enumerate(manager_result.items) if item.kind == "deadline" and item.priority >= 900)
            share_index = next(i for i, item in enumerate(manager_result.items) if item.kind == "returned_share")
            lock_index = next(i for i, item in enumerate(manager_result.items) if item.kind == "document_lock")
            upcoming_index = next(i for i, item in enumerate(manager_result.items) if item.kind == "deadline" and item.priority in (700, 600))
            unknown_index = next(i for i, item in enumerate(manager_result.items) if item.kind == "unknown_date")
            require(critical_index < share_index < lock_index < upcoming_index < unknown_index, "priority order")
            require(len({item.key for item in manager_result.items}) == len(manager_result.items), "duplicate agenda key")
            coexistence = {
                "ordered": [
                    {"kind": item.kind, "priority": item.priority, "key": item.key}
                    for item in manager_result.items
                ],
                "bundle_load_count": len(manager_calls["source"]["load"]),
                "provider_calls": manager_calls["providers"],
            }
            output["coexistence"] = coexistence
            write_json(evidence / "coexistence-priority-smoke.json", coexistence)
            (evidence / "coexistence-priority-smoke.log").write_text("PASS\n", encoding="utf-8")

            state_repository = AgendaStateRepository(db)
            service = StaffAgendaService(db, state_repository=state_repository)
            facade = PersonalAgendaFacade(
                db,
                context_factory=PersonalAgendaContextFactory(now_provider=lambda: NOW),
                agenda_service=service,
                state_repository=state_repository,
            )
            before_lock = dict(
                db.conn.execute(
                    "SELECT * FROM document_locks WHERE contract_id=?",
                    (contracts["own"],),
                ).fetchone()
            )
            first = facade.load(owner, now=NOW, touch_presented=False)
            first_item = next(item for item in first.all_items if item.kind == "document_lock")
            require(first_item.key in first.new_keys, "initial lock not new")
            facade.mark_seen(owner, first_item, seen_at=NOW)
            seen = facade.load(owner, now=NOW, touch_presented=False)
            require(
                any(item.key == first_item.key for item in seen.all_items)
                and first_item.key not in seen.new_keys,
                "seen condition behavior",
            )
            facade.snooze(owner, first_item, until=NOW + timedelta(days=1), now=NOW)
            snoozed = facade.load(owner, now=NOW, touch_presented=False)
            require(
                all(item.key != first_item.key for item in snoozed.all_items)
                and snoozed.snoozed_count >= 1
                and snoozed.filtered_count >= 1,
                "snooze behavior",
            )
            facade.clear_snooze(owner, first_item)
            cleared = facade.load(owner, now=NOW, touch_presented=False)
            require(any(item.key == first_item.key for item in cleared.all_items), "clear snooze")
            after_build_lock = dict(
                db.conn.execute(
                    "SELECT * FROM document_locks WHERE contract_id=?",
                    (contracts["own"],),
                ).fetchone()
            )
            require(before_lock == after_build_lock, "build mutated document_locks")
            with db.tx():
                db.conn.execute(
                    "UPDATE document_locks SET is_locked=0,updated_at=? WHERE contract_id=?",
                    ("2026-07-13 10:00:00", contracts["own"]),
                )
            resolved = facade.load(owner, now=NOW, touch_presented=False)
            require(all(item.key != first_item.key for item in resolved.all_items), "source resolution")
            with db.tx():
                db.conn.execute(
                    """
                    UPDATE document_locks
                    SET is_locked=1,locked_at=?,updated_at=?
                    WHERE contract_id=?
                    """,
                    ("2026-07-13 11:00:00", "2026-07-13 11:00:00", contracts["own"]),
                )
            relocked = facade.load(owner, now=NOW, touch_presented=False)
            relocked_item = next(item for item in relocked.all_items if item.key == first_item.key)
            require(relocked_item.version != first_item.version, "relock version")
            require(relocked_item.key in relocked.new_keys, "relock new version")
            lifecycle = {
                "initial_key": first_item.key,
                "initial_version": first_item.version,
                "relocked_version": relocked_item.version,
                "seen_new_count": seen.new_count,
                "snoozed_count": snoozed.snoozed_count,
                "filtered_count": snoozed.filtered_count,
                "document_lock_unchanged_during_build": before_lock == after_build_lock,
            }
            output["lifecycle"] = lifecycle
            write_json(evidence / "lifecycle-state-smoke.json", lifecycle)
            (evidence / "lifecycle-state-smoke.log").write_text("PASS\n", encoding="utf-8")

            collision_before = dict(
                db.conn.execute(
                    """
                    SELECT * FROM staff_agenda_state
                    WHERE staff_id=? AND agenda_key='collision:seed'
                    """,
                    (staff["owner"],),
                ).fetchone()
            )
            auth.create_system_admin(db.conn, "root", "pw")
            admin_row = auth.verify_system_admin_login(db.conn, "root", "pw")
            admin_session = auth.build_system_admin_session(admin_row, "admin-device")
            require(
                admin_session["id"] == 0
                and admin_session["admin_id"] == staff["owner"]
                and admin_session["is_admin"] is True
                and admin_session["is_active"] == 1
                and "permissions" not in admin_session,
                "system admin session shape",
            )

            def system_guard(session, override=()):
                source_spy = SourceSpy(AgendaSourceRepository(db))
                state_spy = StateSpy(AgendaStateRepository(db))
                providers = [
                    ProviderSpy(provider_class())
                    for provider_class in (
                        DeadlineAgendaProvider,
                        ReturnedShareAgendaProvider,
                        DocumentLockAgendaProvider,
                        UnknownDateAgendaProvider,
                    )
                ]
                factory = PersonalAgendaContextFactory(now_provider=lambda: NOW)
                context = factory.build(session, now=NOW, personal_contract_ids=override)
                service = StaffAgendaService(
                    db,
                    state_repository=state_spy,
                    source_repository=source_spy,
                    providers=providers,
                )
                facade = PersonalAgendaFacade(
                    db,
                    context_factory=factory,
                    agenda_service=service,
                    state_repository=state_spy,
                )
                snapshot = facade.load(
                    session,
                    now=NOW,
                    personal_contract_ids=override,
                    touch_presented=False,
                )
                calls = spy_snapshot(source_spy, state_spy, providers)
                require(context.presentation_profile.code == AgendaPresentationProfileCode.SYSTEM, "system profile")
                require(context.contract_scope == AgendaContractScopeCode.ALL_VISIBLE, "system scope")
                require(context.staff_id is None, "system staff identity")
                require(snapshot.all_items == (), "system result")
                require(calls["source"] == {"personal": [], "all": 0, "load": [], "platform": 0}, "system source calls")
                require(not calls["state"], "system state calls")
                require(
                    all(value == {"is_enabled": 0, "build": 0} for value in calls["providers"].values()),
                    "system provider calls",
                )
                return context, facade, state_spy, calls

            real_context, real_facade, real_state, real_calls = system_guard(admin_session)
            require(real_context.permissions == frozenset(), "system permissions")
            injected = {
                **admin_session,
                "permissions": frozenset(
                    {
                        "view_contracts",
                        "unlock_own_documents",
                        "unlock_all_documents",
                        "edit_contracts",
                    }
                ),
            }
            injected_context, injected_facade, injected_state, injected_calls = system_guard(injected)
            require(injected_context.staff_id is None, "injected system identity")
            _, override_facade, override_state, override_admin_calls = system_guard(
                injected,
                {contracts["critical"]},
            )
            valid_item = next(item for item in manager_result.items if item.kind == "document_lock")
            for session, facade_instance, state_instance in (
                (admin_session, real_facade, real_state),
                (injected, injected_facade, injected_state),
                (injected, override_facade, override_state),
            ):
                for operation in ("mark_seen", "snooze", "clear_snooze"):
                    try:
                        if operation == "mark_seen":
                            facade_instance.mark_seen(session, valid_item, seen_at=NOW)
                        elif operation == "snooze":
                            facade_instance.snooze(
                                session,
                                valid_item,
                                until=NOW + timedelta(days=1),
                                now=NOW,
                            )
                        else:
                            facade_instance.clear_snooze(session, valid_item)
                        raise AssertionError("system interaction unexpectedly succeeded")
                    except AgendaInteractionError:
                        pass
                require(not state_instance.calls, "system interaction reached state repository")
            collision_after = dict(
                db.conn.execute(
                    """
                    SELECT * FROM staff_agenda_state
                    WHERE staff_id=? AND agenda_key='collision:seed'
                    """,
                    (staff["owner"],),
                ).fetchone()
            )
            require(collision_before == collision_after, "numeric collision row mutated")
            system_admin_evidence = {
                "session": admin_session,
                "real_context": {
                    "profile": real_context.presentation_profile.code,
                    "scope": real_context.contract_scope,
                    "staff_id": real_context.staff_id,
                    "permissions": sorted(real_context.permissions),
                },
                "real_calls": real_calls,
                "injected_calls": injected_calls,
                "override_calls": override_admin_calls,
                "collision_before": collision_before,
                "collision_after": collision_after,
            }
            output["system_admin"] = system_admin_evidence
            write_json(evidence / "system-admin-fail-closed.json", system_admin_evidence)
            (evidence / "system-admin-fail-closed.log").write_text("PASS\n", encoding="utf-8")

            snapshot = project_agenda_result(manager_result, compact_limit=2, detail_limit=20)
            require(snapshot.active_count == len(manager_result.items), "presentation active count")
            require(
                dict(manager_result.counts_by_kind).get("document_lock") == len(manager_locks),
                "counts_by_kind document_lock",
            )
            require(any(item.kind == "document_lock" for item in snapshot.compact_items + snapshot.detail_items), "projection missing lock")
            app = QApplication.instance() or QApplication([])
            compact = AgendaCompactWidget()
            compact.set_snapshot(snapshot)
            detail = AgendaDetailWindow()
            detail.set_snapshot(snapshot)
            app.processEvents()
            require(any(row.item.kind == "document_lock" for row in compact._rows + detail._rows), "Qt generic render")
            require(
                all(
                    "unlock_document" not in row.item.action_hints
                    and "lock_document" not in row.item.action_hints
                    for row in compact._rows + detail._rows
                ),
                "Qt direct action",
            )
            qt_evidence = {
                "compact_rows": [row.item.kind for row in compact._rows],
                "detail_rows": [row.item.kind for row in detail._rows],
                "counts_by_kind": dict(manager_result.counts_by_kind),
                "qt_platform": os.getenv("QT_QPA_PLATFORM"),
            }
            output["generic_qt"] = qt_evidence
            write_json(evidence / "generic-Qt-presentation-smoke.json", qt_evidence)
            (evidence / "generic-Qt-presentation-smoke.log").write_text("PASS\n", encoding="utf-8")

        finally:
            db.close()

    write_json(evidence / "runtime-smokes-summary.json", output)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--feature", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()

    baseline = Path(args.baseline).resolve()
    feature = Path(args.feature).resolve()
    evidence = Path(args.evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)

    gates = {}
    errors = []

    try:
        baseline_head = git_output(baseline, "rev-parse", "HEAD")
        feature_head = git_output(feature, "rev-parse", "HEAD")
        changed = [
            line
            for line in git_output(feature, "diff", "--name-only", PRODUCT, feature_head).splitlines()
            if line
        ]
        require(baseline_head == BASELINE, "baseline SHA mismatch")
        require(set(changed) == TEMP_PATHS and len(changed) == 2, "temporary diff allowlist mismatch")
        preflight = {
            "baseline": baseline_head,
            "product_head": PRODUCT,
            "validation_head": feature_head,
            "changed_paths": changed,
        }
        write_json(evidence / "ref-preflight.json", preflight)
        (evidence / "ref-preflight.txt").write_text(dump_text(preflight), encoding="utf-8")
        gates["preflight"] = {"status": "PASS", **preflight}
    except Exception as exc:
        errors.append(f"preflight: {exc!r}")
        gates["preflight"] = {"status": "FAIL", "error": repr(exc)}

    try:
        parity = {
            "baseline": sha_info(baseline / "requirements.txt"),
            "feature": sha_info(feature / "requirements.txt"),
        }
        parity["equal"] = parity["baseline"] == parity["feature"]
        require(parity["equal"], "requirements byte parity failed")
        write_json(evidence / "requirements-parity.json", parity)
        (evidence / "requirements-parity.txt").write_text(dump_text(parity), encoding="utf-8")
        gates["requirements"] = {"status": "PASS", **parity}
    except Exception as exc:
        errors.append(f"requirements: {exc!r}")
        gates["requirements"] = {"status": "FAIL", "error": repr(exc)}

    environment = {
        "platform": platform.platform(),
        "python": sys.version,
        "architecture": platform.architecture(),
        "qt_platform": os.getenv("QT_QPA_PLATFORM"),
    }
    for name, command in (
        ("pip", [sys.executable, "-m", "pip", "--version"]),
        ("pytest", [sys.executable, "-m", "pytest", "--version"]),
        ("pyside6", [sys.executable, "-c", "import PySide6; print(PySide6.__version__)"]),
    ):
        result = run(command, feature, evidence / f"environment-{name}.log")
        environment[name] = {"exit": result.returncode, "output": result.stdout.strip()}
        if result.returncode != 0:
            errors.append(f"environment {name}")
    write_json(evidence / "environment.json", environment)
    (evidence / "environment.txt").write_text(dump_text(environment), encoding="utf-8")
    environment_ok = all(environment[name]["exit"] == 0 for name in ("pip", "pytest", "pyside6"))
    gates["environment"] = {"status": "PASS" if environment_ok else "FAIL", **environment}

    compile_result = run(
        [sys.executable, "-m", "compileall", "-q", "src", "tests"],
        feature,
        evidence / "compile.log",
    )
    gates["compile"] = {
        "status": "PASS" if compile_result.returncode == 0 else "FAIL",
        "exit": compile_result.returncode,
        "command": "python -m compileall -q src tests",
    }
    if compile_result.returncode != 0:
        errors.append("compile")

    targeted_files = [
        "tests/test_agenda_source_repository.py",
        "tests/test_document_lock_agenda_provider.py",
        "tests/test_staff_agenda_service.py",
        "tests/test_agenda_context_factory.py",
        "tests/test_personal_agenda_facade.py",
        "tests/test_deadline_agenda_provider.py",
        "tests/test_unknown_date_agenda_provider.py",
        "tests/test_returned_share_agenda_provider.py",
        "tests/test_agenda_lifecycle.py",
        "tests/test_agenda_models.py",
    ]
    targeted_xml = evidence / "static-targeted.xml"
    targeted_command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *targeted_files,
        f"--junitxml={targeted_xml}",
    ]
    targeted_result = run(
        targeted_command,
        feature,
        evidence / "static-targeted.log",
        {"QT_QPA_PLATFORM": "offscreen"},
    )
    try:
        targeted_summary = junit_summary(targeted_xml)
    except Exception as exc:
        targeted_summary = {
            "tests": 0,
            "passed": 0,
            "failures": 0,
            "errors": 1,
            "skipped": 0,
            "nodes": [],
            "parse_valid": False,
            "parse_error": repr(exc),
        }
    targeted_ok = (
        targeted_result.returncode == 0
        and targeted_summary["parse_valid"]
        and targeted_summary["tests"] > 0
        and targeted_summary["failures"] == 0
        and targeted_summary["errors"] == 0
    )
    gates["static_targeted"] = {
        "status": "PASS" if targeted_ok else "FAIL",
        "exit": targeted_result.returncode,
        "command": subprocess.list2cmdline(targeted_command),
        **targeted_summary,
    }
    if not targeted_ok:
        errors.append("static targeted")

    for gate_name, relative_path, required_text in (
        ("schema_smoke", "tests/smoke_sts_agenda_schema.py", "schema_version=18"),
        ("database_smoke", "tests/smoke_sts_database.py", "ok"),
    ):
        if not (feature / relative_path).exists():
            gates[gate_name] = {"status": "FAIL", "error": "missing"}
            errors.append(gate_name)
            continue
        result = run(
            [sys.executable, relative_path],
            feature,
            evidence / f"{gate_name.replace('_', '-')}.log",
        )
        passed = result.returncode == 0 and required_text in result.stdout
        gates[gate_name] = {
            "status": "PASS" if passed else "FAIL",
            "exit": result.returncode,
            "required_text": required_text,
            "tail": result.stdout[-2000:],
        }
        if not passed:
            errors.append(gate_name)

    try:
        runtime_validation(feature, evidence)
        for gate_name in (
            "document_lock_source",
            "permission_matrix",
            "item_contract",
            "coexistence_priority",
            "lifecycle_state",
            "system_admin",
            "generic_qt",
        ):
            gates[gate_name] = {"status": "PASS"}
    except Exception as exc:
        errors.append(f"runtime smokes: {exc!r}")
        for gate_name in (
            "document_lock_source",
            "permission_matrix",
            "item_contract",
            "coexistence_priority",
            "lifecycle_state",
            "system_admin",
            "generic_qt",
        ):
            gates[gate_name] = {"status": "FAIL", "error": repr(exc)}
        (evidence / "runtime-error.log").write_text(traceback.format_exc(), encoding="utf-8")

    full = {}
    for name, cwd in (("baseline", baseline), ("feature", feature)):
        junit_path = evidence / f"{name}-full.xml"
        result = run(
            [sys.executable, "-m", "pytest", "-q", f"--junitxml={junit_path}"],
            cwd,
            evidence / f"{name}-full.log",
            {"QT_QPA_PLATFORM": "offscreen"},
        )
        try:
            summary = junit_summary(junit_path)
        except Exception as exc:
            summary = {
                "tests": 0,
                "passed": 0,
                "failures": 0,
                "errors": 1,
                "skipped": 0,
                "nodes": [],
                "parse_valid": False,
                "parse_error": repr(exc),
            }
        valid = (
            result.returncode in (0, 1)
            and summary["parse_valid"]
            and summary["tests"] > 0
        )
        full[name] = {"valid": valid, "exit": result.returncode, **summary}
        if not valid:
            errors.append(f"{name} full")

    baseline_nodes = set(full["baseline"]["nodes"])
    feature_nodes = set(full["feature"]["nodes"])
    feature_only = sorted(feature_nodes - baseline_nodes)
    baseline_only = sorted(baseline_nodes - feature_nodes)
    differential = {
        "baseline": full["baseline"],
        "feature": full["feature"],
        "feature_only": feature_only,
        "feature_only_count": len(feature_only),
        "baseline_only": baseline_only,
        "baseline_only_count": len(baseline_only),
    }
    write_json(evidence / "differential-summary.json", differential)
    (evidence / "differential-summary.txt").write_text(
        dump_text(differential),
        encoding="utf-8",
    )
    differential_ok = (
        full["baseline"]["valid"]
        and full["feature"]["valid"]
        and not feature_only
    )
    gates["differential"] = {
        "status": "PASS" if differential_ok else "FAIL",
        **differential,
    }
    if not differential_ok:
        errors.append("differential")

    final_ok = not errors and all(value["status"] == "PASS" for value in gates.values())
    summary = {
        "status": "PASS" if final_ok else "FAIL",
        "gates": gates,
        "errors": errors,
    }
    write_json(evidence / "validation-summary.json", summary)
    (evidence / "validation-summary.txt").write_text(dump_text(summary), encoding="utf-8")

    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        lines = [
            "# Agenda Stage 4B-V",
            "",
            f"**Final: {summary['status']}**",
            "",
            "| Gate | Result |",
            "|---|---|",
        ]
        lines.extend(f"| {name} | {value['status']} |" for name, value in gates.items())
        Path(step_summary).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0 if final_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
