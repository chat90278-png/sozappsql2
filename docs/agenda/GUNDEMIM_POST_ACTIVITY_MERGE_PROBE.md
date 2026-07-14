# Gündemim Post-Activity Merge Probe

- target_branch: `integration/gundemim-after-activity-20260714`
- target_head: `b35990380df46ad0fe109aaf35c4bc09d4cf41de`
- source_branch: `integration/gundemim-current-main-20260713`
- source_head: `66681d51877ad09db7379b6bbd7049a7436af1fc`
- merge_base: `e1ed9a66318e19178f132602d3114a97880fa27f`
- merge_exit: `1`

## Unmerged paths
```text
src/services/sts_database.py
src/services/sts_schema_upgrade.py
src/services/sts_schema_upgrade_gate.py
tests/test_sts_schema_upgrade.py
tests/test_sts_schema_upgrade_gate.py
```

## Merge status
```text
A  docs/agenda/AGENDA_FOUNDATION_IMPLEMENTATION_PLAN.md
A  docs/agenda/AGENDA_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_SOURCE_OF_TRUTH_AUDIT.md
A  docs/agenda/AGENDA_STAGE_02A_PERSONAL_CONDITION_ENGINE.md
A  docs/agenda/AGENDA_STAGE_02A_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_02B_APPLICATION_FACADE.md
A  docs/agenda/AGENDA_STAGE_02B_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_03A_PERSONAL_QT_UI.md
A  docs/agenda/AGENDA_STAGE_03A_RUNTIME_VISUAL_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_03B_RETURNED_SHARE_PROVIDER.md
A  docs/agenda/AGENDA_STAGE_03B_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_04A_MULTI_PROFILE_SCOPE.md
A  docs/agenda/AGENDA_STAGE_04A_R1_SYSTEM_ADMIN_IDENTITY.md
A  docs/agenda/AGENDA_STAGE_04A_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_04B_DOCUMENT_LOCK_PROVIDER.md
A  docs/agenda/AGENDA_STAGE_04B_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_04C_CONTRACT_ACTIVITY_PROVIDER.md
A  docs/agenda/AGENDA_STAGE_04C_R1_EXECUTION_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_04C_RUNTIME_VALIDATION.md
A  docs/agenda/AGENDA_STAGE_05B_CONTROLLED_INTEGRATION.md
A  docs/agenda/AGENDA_TRANSACTION_DECISION.md
A  src/domain/agenda/__init__.py
A  src/domain/agenda/activity.py
A  src/domain/agenda/constants.py
A  src/domain/agenda/deadline_stage.py
A  src/domain/agenda/keys.py
A  src/domain/agenda/lifecycle.py
A  src/domain/agenda/models.py
A  src/domain/agenda/presentation.py
A  src/domain/agenda/priority.py
A  src/domain/agenda/providers/__init__.py
A  src/domain/agenda/providers/activity.py
A  src/domain/agenda/providers/base.py
A  src/domain/agenda/providers/deadline.py
A  src/domain/agenda/providers/document_lock.py
A  src/domain/agenda/providers/returned_share.py
A  src/domain/agenda/providers/unknown_date.py
A  src/domain/agenda/source_models.py
A  src/services/agenda_context_factory.py
A  src/services/agenda_source_repository.py
A  src/services/agenda_state_repository.py
A  src/services/personal_agenda_facade.py
A  src/services/staff_agenda_service.py
UU src/services/sts_database.py
UU src/services/sts_schema_upgrade.py
UU src/services/sts_schema_upgrade_gate.py
A  src/ui/agenda_compact_widget.py
A  src/ui/agenda_detail_window.py
M  src/ui/main_page_analysis_window.py
A  tests/smoke_sts_agenda_schema.py
M  tests/smoke_sts_database.py
A  tests/test_activity_agenda_provider.py
A  tests/test_agenda_compact_widget.py
A  tests/test_agenda_context_factory.py
A  tests/test_agenda_current_main_composition.py
A  tests/test_agenda_deadline_stage.py
A  tests/test_agenda_detail_window.py
A  tests/test_agenda_keys.py
A  tests/test_agenda_lifecycle.py
A  tests/test_agenda_models.py
A  tests/test_agenda_presentation.py
A  tests/test_agenda_schema_v18_integration.py
A  tests/test_agenda_source_repository.py
A  tests/test_agenda_startup_upgrade_integration.py
A  tests/test_agenda_state_repository.py
A  tests/test_deadline_agenda_provider.py
A  tests/test_document_lock_agenda_provider.py
A  tests/test_main_page_agenda_integration.py
A  tests/test_personal_agenda_facade.py
A  tests/test_returned_share_agenda_provider.py
A  tests/test_staff_agenda_service.py
A  tests/test_sts_database_transactions.py
UU tests/test_sts_schema_upgrade.py
UU tests/test_sts_schema_upgrade_gate.py
A  tests/test_unknown_date_agenda_provider.py
?? merge-probe.md
```

## Conflict regions

### `src/services/sts_database.py`

Region 1, lines 66-264:
```text
00066:     return '"' + str(identifier or "").replace('"', '""') + '"'
00067: 
00068: 
00069: LEGACY_CONTRACT_PARENT_NO_COLUMN = "parent_contract_" "no"
00070: LEGACY_CONTRACT_USERS_COLUMN = "user_" "names"
00071: LEGACY_DELIVERY_SYSTEM_LABEL_COLUMN = "system_" "name"
00072: CURRENT_SCHEMA_VERSION = 18
00073: 
00074: <<<<<<< HEAD
00075: ACTIVITY_LOG_COLUMNS: tuple[tuple[str, str], ...] = (
00076:     ("occurred_at_utc", "TEXT"),
00077:     ("category", "TEXT"),
00078:     ("status", "TEXT"),
00079:     ("operation_id", "TEXT"),
00080:     ("actor_type", "TEXT"),
00081:     ("actor_staff_id", "INTEGER"),
00082:     ("actor_admin_id", "INTEGER"),
00083:     ("actor_display_name", "TEXT"),
00084:     ("session_id", "TEXT"),
00085:     ("contract_id", "INTEGER"),
00086:     ("platform_name_snapshot", "TEXT"),
00087:     ("contract_no_snapshot", "TEXT"),
00088:     ("changed_fields_json", "TEXT"),
00089:     ("technical_payload_json", "TEXT"),
00090:     ("event_schema_version", "INTEGER DEFAULT 1"),
00091: )
00092: 
00093: ACTIVITY_LOG_INDEX_SQL: tuple[str, ...] = (
00094:     "CREATE INDEX IF NOT EXISTS idx_activity_logs_occurred_id ON activity_logs(occurred_at_utc DESC, id DESC)",
00095:     "CREATE INDEX IF NOT EXISTS idx_activity_logs_category_occurred ON activity_logs(category, occurred_at_utc DESC)",
00096:     "CREATE INDEX IF NOT EXISTS idx_activity_logs_actor_staff_occurred ON activity_logs(actor_staff_id, occurred_at_utc DESC)",
00097:     "CREATE INDEX IF NOT EXISTS idx_activity_logs_operation_id ON activity_logs(operation_id)",
00098:     "CREATE INDEX IF NOT EXISTS idx_activity_logs_action_occurred ON activity_logs(action, occurred_at_utc DESC)",
00099:     "CREATE INDEX IF NOT EXISTS idx_activity_logs_entity_occurred ON activity_logs(entity_type, entity_id, occurred_at_utc DESC)",
00100:     "CREATE INDEX IF NOT EXISTS idx_activity_logs_contract_occurred ON activity_logs(contract_id, occurred_at_utc DESC)",
00101:     "CREATE INDEX IF NOT EXISTS idx_activity_logs_platform_occurred ON activity_logs(platform_id, occurred_at_utc DESC)",
00102: )
00103: =======
00104: AGENDA_STATE_COLUMNS: tuple[str, ...] = (
00105:     "staff_id", "agenda_key", "first_presented_at", "last_presented_at",
00106:     "seen_at", "seen_version", "snoozed_until", "snoozed_version",
00107:     "snoozed_severity", "dismissed_at", "dismissed_version",
00108:     "created_at", "updated_at",
00109: )
00110: 
00111: AGENDA_STATE_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
00112:     ("idx_staff_agenda_state_staff", ("staff_id",)),
00113:     ("idx_staff_agenda_state_snoozed", ("staff_id", "snoozed_until")),
00114: )
00115: 
00116: 
00117: def _agenda_table_exists(conn: sqlite3.Connection, table: str) -> bool:
00118:     return conn.execute(
00119:         "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
00120:         (str(table or ""),),
00121:     ).fetchone() is not None
00122: 
00123: 
00124: def _agenda_table_info(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row | tuple]:
00125:     if not _agenda_table_exists(conn, table):
00126:         return []
00127:     return list(conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall())
00128: 
00129: 
00130: def _agenda_index_columns(conn: sqlite3.Connection, index_name: str) -> tuple[str, ...]:
00131:     return tuple(
00132:         str(row[2])
00133:         for row in conn.execute(
00134:             f"PRAGMA index_info({quote_identifier(index_name)})"
00135:         ).fetchall()
00136:     )
00137: 
00138: 
00139: def ensure_staff_agenda_state_schema(
00140:     conn: sqlite3.Connection,
00141: ) -> tuple[str, ...]:
00142:     # Caller owns transaction, commit and rollback behavior.
00143:     staff_columns = {
00144:         str(row[1])
00145:         for row in _agenda_table_info(conn, "staff")
00146:     }
00147:     if "id" not in staff_columns:
00148:         raise RuntimeError(
00149:             "staff_agenda_state oluşturulamadı: "
00150:             "staff tablosu veya staff.id eksik."
00151:         )
00152:     if _agenda_table_exists(conn, "agenda_items"):
00153:         raise RuntimeError("Yasak agenda_items tablosu tespit edildi.")
00154: 
00155:     created: list[str] = []
00156:     table_existed = _agenda_table_exists(conn, "staff_agenda_state")
00157:     conn.execute(
00158:         """
00159:         CREATE TABLE IF NOT EXISTS staff_agenda_state(
00160:             staff_id INTEGER NOT NULL,
00161:             agenda_key TEXT NOT NULL,
00162:             first_presented_at TEXT,
00163:             last_presented_at TEXT,
00164:             seen_at TEXT,
00165:             seen_version TEXT NOT NULL DEFAULT '',
00166:             snoozed_until TEXT,
00167:             snoozed_version TEXT NOT NULL DEFAULT '',
00168:             snoozed_severity TEXT NOT NULL DEFAULT '',
00169:             dismissed_at TEXT,
00170:             dismissed_version TEXT NOT NULL DEFAULT '',
00171:             created_at TEXT,
00172:             updated_at TEXT,
00173:             PRIMARY KEY(staff_id, agenda_key),
00174:             FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE
00175:         )
00176:         """
00177:     )
00178:     if not table_existed:
00179:         created.append("staff_agenda_state")
00180: 
00181:     # Fail closed on malformed pre-existing tables before attempting indexes.
00182:     table_info = _agenda_table_info(conn, "staff_agenda_state")
00183:     actual_columns = tuple(str(row[1]) for row in table_info)
00184:     if actual_columns != AGENDA_STATE_COLUMNS:
00185:         raise RuntimeError(
00186:             "staff_agenda_state kolon sözleşmesi geçersiz: "
00187:             f"expected={AGENDA_STATE_COLUMNS}; actual={actual_columns}"
00188:         )
00189: 
00190:     primary_key = tuple(
00191:         str(row[1])
00192:         for row in sorted(
00193:             (row for row in table_info if int(row[5] or 0) > 0),
00194:             key=lambda row: int(row[5]),
00195:         )
00196:     )
00197:     if primary_key != ("staff_id", "agenda_key"):
00198:         raise RuntimeError(
00199:             "staff_agenda_state primary key sözleşmesi geçersiz: "
00200:             f"expected=('staff_id', 'agenda_key'); actual={primary_key}"
00201:         )
00202: 
00203:     foreign_keys = [
00204:         (str(row[3]), str(row[2]), str(row[4]), str(row[6]).upper())
00205:         for row in conn.execute(
00206:             'PRAGMA foreign_key_list("staff_agenda_state")'
00207:         ).fetchall()
00208:     ]
00209:     expected_fk = ("staff_id", "staff", "id", "CASCADE")
00210:     if foreign_keys != [expected_fk]:
00211:         raise RuntimeError(
00212:             "staff_agenda_state foreign key sözleşmesi geçersiz: "
00213:             f"expected={expected_fk}; actual={foreign_keys}"
00214:         )
00215: 
00216:     existing_indexes = {
00217:         str(row[0])
00218:         for row in conn.execute(
00219:             "SELECT name FROM sqlite_master WHERE type='index'"
00220:         ).fetchall()
00221:     }
00222:     conn.execute(
00223:         "CREATE INDEX IF NOT EXISTS idx_staff_agenda_state_staff "
00224:         "ON staff_agenda_state(staff_id)"
00225:     )
00226:     conn.execute(
00227:         "CREATE INDEX IF NOT EXISTS idx_staff_agenda_state_snoozed "
00228:         "ON staff_agenda_state(staff_id,snoozed_until)"
00229:     )
00230:     for index_name, _columns in AGENDA_STATE_INDEXES:
00231:         if index_name not in existing_indexes:
00232:             created.append(index_name)
00233: 
00234:     current_indexes = {
00235:         str(row[0])
00236:         for row in conn.execute(
00237:             "SELECT name FROM sqlite_master WHERE type='index'"
00238:         ).fetchall()
00239:     }
00240:     for index_name, expected_columns in AGENDA_STATE_INDEXES:
00241:         if index_name not in current_indexes:
00242:             raise RuntimeError(
00243:                 f"staff_agenda_state index eksik: {index_name}"
00244:             )
00245:         actual_index_columns = _agenda_index_columns(conn, index_name)
00246:         if actual_index_columns != expected_columns:
00247:             raise RuntimeError(
00248:                 f"{index_name} kolon sırası geçersiz: "
00249:                 f"expected={expected_columns}; "
00250:                 f"actual={actual_index_columns}"
00251:             )
00252: 
00253:     if _agenda_table_exists(conn, "agenda_items"):
00254:         raise RuntimeError("Yasak agenda_items tablosu tespit edildi.")
00255:     return tuple(created)
00256: >>>>>>> origin/integration/gundemim-current-main-20260713
00257: 
00258: 
00259: class STSMigrationError(RuntimeError):
00260:     """Raised when a legacy STS schema cannot be safely migrated."""
00261: 
00262:     def __init__(self, user_message: str, *, backup_path: Path | None = None, technical_detail: str = ""):
00263:         super().__init__(user_message)
00264:         self.user_message = user_message
```

Region 2, lines 421-475:
```text
00421:         try:
00422:             self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
00423:         except Exception:
00424:             pass
00425:         self.conn.close()
00426: 
00427:     @contextmanager
00428:     def tx(self):
00429: <<<<<<< HEAD
00430:         """Own the outer transaction and use unique savepoints for nesting."""
00431:         owns_transaction = not self.conn.in_transaction
00432:         savepoint: str | None = None
00433:         self._tx_depth += 1
00434:         try:
00435:             if owns_transaction:
00436:                 self.conn.execute("BEGIN")
00437:             else:
00438:                 self._savepoint_counter += 1
00439:                 savepoint = f"_sts_tx_{id(self):x}_{self._savepoint_counter}"
00440:                 self.conn.execute(f"SAVEPOINT {savepoint}")
00441:             yield
00442:             if savepoint:
00443:                 self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
00444:             elif owns_transaction:
00445: =======
00446:         """Transaction context manager.
00447: 
00448:         Ust uste cagrildiginda (ornegin batch_save() icinde write_contract())
00449:         ic cagrı SAVEPOINT kullanir — dis transaction'i erken kapatmaz.
00450:         Bu sayede dis kod rollback yapabilir, atomicity korunur.
00451:         """
00452:         if self.conn.in_transaction:
00453:             # Zaten acik bir transaction var — SAVEPOINT ile ic transaction ac
00454:             sp = f"_tx_{id(self) & 0xFFFF}"
00455:             self.conn.execute(f"SAVEPOINT {sp}")
00456:             try:
00457:                 yield
00458:                 self.conn.execute(f"RELEASE SAVEPOINT {sp}")
00459:             except Exception:
00460:                 self.conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
00461:                 self.conn.execute(f"RELEASE SAVEPOINT {sp}")
00462:                 raise
00463:         else:
00464:             self.conn.execute("BEGIN")
00465:             try:
00466:                 yield
00467: >>>>>>> origin/integration/gundemim-current-main-20260713
00468:                 self.conn.commit()
00469:         except Exception:
00470:             if savepoint:
00471:                 try:
00472:                     self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
00473:                 finally:
00474:                     self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
00475:             elif owns_transaction:
```

### `src/services/sts_schema_upgrade.py`

Region 1, lines 180-225:
```text
00180:         conn,
00181:         "share_packages",
00182:         "cancelled_by_full_name",
00183:         "TEXT NOT NULL DEFAULT ''",
00184:     )
00185: 
00186: 
00187: def _migrate_17_to_18(conn: sqlite3.Connection) -> None:
00188: <<<<<<< HEAD
00189:     conn.execute(
00190:         """
00191:         CREATE TABLE IF NOT EXISTS activity_logs(
00192:             id INTEGER PRIMARY KEY AUTOINCREMENT,
00193:             created_at TEXT NOT NULL,
00194:             actor TEXT,
00195:             source TEXT,
00196:             device_name TEXT,
00197:             action TEXT NOT NULL,
00198:             entity_type TEXT,
00199:             entity_id TEXT,
00200:             entity_key TEXT,
00201:             platform_id INTEGER,
00202:             contract_no TEXT,
00203:             message TEXT,
00204:             before_json TEXT,
00205:             after_json TEXT,
00206:             payload_json TEXT
00207:         )
00208:         """
00209:     )
00210:     _require_columns(conn, "activity_logs", {"id", "created_at", "action"})
00211:     for name, ddl in ACTIVITY_LOG_COLUMNS:
00212:         _ensure_column(conn, "activity_logs", name, ddl)
00213:     for sql in ACTIVITY_LOG_INDEX_SQL:
00214:         conn.execute(sql)
00215: =======
00216:     ensure_staff_agenda_state_schema(conn)
00217: >>>>>>> origin/integration/gundemim-current-main-20260713
00218: 
00219: 
00220: MIGRATIONS: tuple[MigrationStep, ...] = (
00221:     MigrationStep(14, 15, "v14_to_v15_share_package_registry", _migrate_14_to_15),
00222:     MigrationStep(15, 16, "v15_to_v16_merge_result_audit", _migrate_15_to_16),
00223:     MigrationStep(16, 17, "v16_to_v17_share_cancellation_audit", _migrate_16_to_17),
00224: <<<<<<< HEAD
00225:     MigrationStep(17, 18, "v17_to_v18_activity_history_infrastructure", _migrate_17_to_18),
```

### `src/services/sts_schema_upgrade_gate.py`

Region 1, lines 186-258:
```text
00186: 
00187: _V17_COLUMNS = (
00188:     "cancelled_at",
00189:     "cancelled_by_staff_id",
00190:     "cancelled_by_username",
00191:     "cancelled_by_full_name",
00192: )
00193: 
00194: <<<<<<< HEAD
00195: _V18_ACTIVITY_COLUMNS = (
00196:     "occurred_at_utc",
00197:     "category",
00198:     "status",
00199:     "operation_id",
00200:     "actor_type",
00201:     "actor_staff_id",
00202:     "actor_admin_id",
00203:     "actor_display_name",
00204:     "session_id",
00205:     "contract_id",
00206:     "platform_name_snapshot",
00207:     "contract_no_snapshot",
00208:     "changed_fields_json",
00209:     "technical_payload_json",
00210:     "event_schema_version",
00211: )
00212: 
00213: _V18_ACTIVITY_INDEXES = (
00214:     "idx_activity_logs_occurred_id",
00215:     "idx_activity_logs_category_occurred",
00216:     "idx_activity_logs_actor_staff_occurred",
00217:     "idx_activity_logs_operation_id",
00218:     "idx_activity_logs_action_occurred",
00219:     "idx_activity_logs_entity_occurred",
00220:     "idx_activity_logs_contract_occurred",
00221:     "idx_activity_logs_platform_occurred",
00222: )
00223: 
00224: FINGERPRINT_MIN_VERSION = VERSIONED_MIGRATION_FLOOR
00225: FINGERPRINT_MAX_VERSION = CURRENT_SCHEMA_VERSION
00226: =======
00227: _V18_AGENDA_STATE_COLUMNS = (
00228:     "staff_id",
00229:     "agenda_key",
00230:     "first_presented_at",
00231:     "last_presented_at",
00232:     "seen_at",
00233:     "seen_version",
00234:     "snoozed_until",
00235:     "snoozed_version",
00236:     "snoozed_severity",
00237:     "dismissed_at",
00238:     "dismissed_version",
00239:     "created_at",
00240:     "updated_at",
00241: )
00242: 
00243: _V18_INDEXES = (
00244:     "idx_staff_agenda_state_staff",
00245:     "idx_staff_agenda_state_snoozed",
00246: )
00247: 
00248: FINGERPRINT_MIN_VERSION = VERSIONED_MIGRATION_FLOOR
00249: FINGERPRINT_MAX_VERSION = 18
00250: >>>>>>> origin/integration/gundemim-current-main-20260713
00251: FINGERPRINT_VERSIONS = tuple(
00252:     range(FINGERPRINT_MIN_VERSION, FINGERPRINT_MAX_VERSION + 1)
00253: )
00254: 
00255: 
00256: def _emit(
00257:     progress_callback: ProgressCallback | None,
00258:     percent: int,
```

Region 2, lines 305-348:
```text
00305:         )
00306:     if version >= 17:
00307:         columns = _merge_required_columns(
00308:             columns,
00309:             "share_packages",
00310:             _V17_COLUMNS,
00311:         )
00312:     if version >= 18:
00313: <<<<<<< HEAD
00314:         columns = _merge_required_columns(
00315:             columns,
00316:             "activity_logs",
00317:             _V18_ACTIVITY_COLUMNS,
00318:         )
00319:         indexes.update(_V18_ACTIVITY_INDEXES)
00320: =======
00321:         columns = _merge_required_columns(columns, "staff", ("id",))
00322:         columns = _merge_required_columns(
00323:             columns,
00324:             "staff_agenda_state",
00325:             _V18_AGENDA_STATE_COLUMNS,
00326:         )
00327:         indexes.update(_V18_INDEXES)
00328:         primary_keys = (("staff_agenda_state", ("staff_id", "agenda_key")),)
00329:         foreign_keys = (
00330:             ("staff_agenda_state", "staff_id", "staff", "id", "CASCADE"),
00331:         )
00332:         index_columns = (
00333:             ("idx_staff_agenda_state_staff", ("staff_id",)),
00334:             (
00335:                 "idx_staff_agenda_state_snoozed",
00336:                 ("staff_id", "snoozed_until"),
00337:             ),
00338:         )
00339:         forbidden_tables = ("agenda_items",)
00340: >>>>>>> origin/integration/gundemim-current-main-20260713
00341: 
00342:     return SchemaFingerprint(
00343:         version=version,
00344:         required_columns=columns,
00345:         required_indexes=tuple(sorted(indexes)),
00346:         required_metadata=(("sts_metadata", "sts_instance_id"),),
00347:         required_primary_keys=primary_keys,
00348:         required_foreign_keys=foreign_keys,
```

### `tests/test_sts_schema_upgrade.py`

Region 1, lines 181-201:
```text
00181: 
00182:     assert result.status == "upgraded"
00183:     assert result.from_version == 14
00184:     assert result.to_version == CURRENT_SCHEMA_VERSION == 18
00185:     assert result.applied_migrations == (
00186:         "v14_to_v15_share_package_registry",
00187:         "v15_to_v16_merge_result_audit",
00188:         "v16_to_v17_share_cancellation_audit",
00189: <<<<<<< HEAD
00190:         "v17_to_v18_activity_history_infrastructure",
00191: =======
00192:         "v17_to_v18_staff_agenda_state",
00193: >>>>>>> origin/integration/gundemim-current-main-20260713
00194:     )
00195:     assert result.backup_path is not None
00196:     assert result.backup_path.exists()
00197:     assert result.backup_path.parent.name == "yedekler"
00198:     assert read_sts_schema_version(result.backup_path) == 14
00199:     assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION
00200: 
00201:     expected_columns = {
```

Region 2, lines 215-235:
```text
00215: def test_v16_runs_v16_to_v17_and_v17_to_v18(tmp_path: Path):
00216:     path = tmp_path / "v16.sts"
00217:     _create_versioned_db(path, 16)
00218: 
00219:     result = upgrade.upgrade_sts_file(path)
00220: 
00221:     assert result.applied_migrations == (
00222:         "v16_to_v17_share_cancellation_audit",
00223: <<<<<<< HEAD
00224:         "v17_to_v18_activity_history_infrastructure",
00225: =======
00226:         "v17_to_v18_staff_agenda_state",
00227: >>>>>>> origin/integration/gundemim-current-main-20260713
00228:     )
00229:     assert read_sts_schema_version(path) == 18
00230:     assert {
00231:         "cancelled_at",
00232:         "cancelled_by_staff_id",
00233:         "cancelled_by_username",
00234:         "cancelled_by_full_name",
00235:     } <= _columns(path, "share_packages")
```

### `tests/test_sts_schema_upgrade_gate.py`

Region 1, lines 263-283:
```text
00263: def test_v16_upgrade_is_postflight_validated_as_current_schema(tmp_path: Path):
00264:     path = tmp_path / "realistic-v16.sts"
00265:     _make_historical_database(path, 16)
00266: 
00267:     result = gate.upgrade_sts_file(path)
00268: 
00269:     assert result.applied_migrations == (
00270:         "v16_to_v17_share_cancellation_audit",
00271: <<<<<<< HEAD
00272:         "v17_to_v18_activity_history_infrastructure",
00273: =======
00274:         "v17_to_v18_staff_agenda_state",
00275: >>>>>>> origin/integration/gundemim-current-main-20260713
00276:     )
00277:     assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION
00278:     assert (
00279:         gate.validate_versioned_schema_fingerprint(
00280:             path,
00281:             CURRENT_SCHEMA_VERSION,
00282:         ).version
00283:         == CURRENT_SCHEMA_VERSION
```
