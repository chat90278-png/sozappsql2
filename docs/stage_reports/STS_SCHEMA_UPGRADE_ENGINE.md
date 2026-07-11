# STS Schema Upgrade Engine — Branch Handoff Report

## Branch and isolation

- Feature branch: `feat/automatic-sts-schema-upgrade-engine`
- Source baseline: `main` commit `2931fa267560397d4d849d6365acde504f376775`
- The branch was developed without merging into `main` and without writing to other active branches.
- The validation-only draft PR `#308` was closed without merge after CI evidence was collected.
- A temporary GitHub Actions workflow used only for branch validation was removed from the feature diff after the validation run.

## Problem addressed

The repository already had important migration safeguards in `STSDatabase`: migration backups, compatibility DDL, integrity checks, foreign-key checks, future-schema rejection, and restore-on-failure behavior. However, historical migrations were concentrated inside `STSDatabase.init_schema()` as unconditional/idempotent schema-building blocks and the method ultimately stamped `meta.schema_version` with the current version.

That structure made it difficult to prove the exact sequence of versioned upgrades and allowed a database whose `schema_version` label did not match its physical schema to be silently repaired by the broad compatibility path.

This branch adds an explicit, deterministic upgrade owner at the user-file open boundary while preserving the existing legacy compatibility engine for historical versions whose exact version boundaries have not yet been extracted.

## Production changes

### `src/services/sts_schema_upgrade.py`

Adds the central versioned upgrade engine.

Registered historical chain:

- v14 → v15: `v14_to_v15_share_package_registry`
- v15 → v16: `v15_to_v16_merge_result_audit`
- v16 → v17: `v16_to_v17_share_cancellation_audit`

The boundaries were checked against the real historical repository changes that introduced schema v15, v16, and v17.

Versioned upgrade behavior:

1. Read the source `meta.schema_version` without mutation.
2. Reject a schema newer than `CURRENT_SCHEMA_VERSION`.
3. Return a no-op for the current schema.
4. Build a contiguous migration chain from the registry.
5. Create a SQLite-consistent backup with the SQLite backup API.
6. Validate the backup before mutation.
7. Open the source database and acquire `BEGIN IMMEDIATE`.
8. Run each migration step in order and advance `schema_version` after each step.
9. Run integrity, foreign-key, and target-version checks inside the transaction.
10. Commit and close the writable connection.
11. Reopen the database read-only and repeat final integrity, foreign-key, and target-version validation.

Recovery behavior is rollback-first:

- Backup creation failure: no migration starts and the source remains untouched.
- Failure before `BEGIN IMMEDIATE`: no physical restore is performed because the migration did not start.
- Failure inside an uncommitted transaction: rollback is attempted and the original source is validated at its original schema version.
- If the rollback validates, the source file is preserved in place and no backup copy is written over it.
- Backup restore is a last-resort fallback only when rollback cannot be validated or a committed/post-commit state fails final validation.

Older/unversioned databases remain delegated to the existing `STSDatabase` compatibility path. The branch deliberately does not invent unsupported v1→v13 historical boundaries.

### `src/services/sts_schema_upgrade_gate.py`

Adds a schema fingerprint gate around the upgrade engine.

For versioned v14–v17 databases the gate verifies that the declared `schema_version` matches a historically valid physical schema before any backup or migration starts.

The fingerprint checks:

- required tables,
- required columns,
- required indexes,
- non-empty `sts_metadata.sts_instance_id`,
- SQLite integrity,
- foreign-key integrity,
- exact declared schema version.

The v14 base fingerprint includes the normalized STS core, multi-platform schema, delivery unit tracking, delivery schedule revision tables, platform delivery report tables, responsible-engineer relation, document folder/file structure, merge UID/revision foundation, and the corresponding merge UID indexes that already existed at the historical v14 boundary.

v15, v16, and v17 extend that base with only the schema elements introduced at those historical boundaries.

The gate runs twice for a successful versioned upgrade:

- preflight against the source version,
- postflight against `CURRENT_SCHEMA_VERSION`.

A database labeled v17 but physically shaped like v16 is rejected instead of being treated as a current no-op.

`FINGERPRINT_MAX_VERSION` is intentionally explicit. A future `CURRENT_SCHEMA_VERSION` bump without a matching fingerprint contract fails tests/runtime closed instead of silently accepting an unvalidated schema version.

### `src/workers/sts_load_worker.py`

The user-file open worker now calls the guarded upgrade entrypoint:

`src.services.sts_schema_upgrade_gate.upgrade_sts_file`

The existing SQLite thread-affinity rule is preserved. No `STSStore`, `STSDatabase`, or SQLite connection created in the worker is sent to the main thread.

The open ownership boundary remains:

1. `MainWindow.start_sts_load()` creates `STSLoadWorker`.
2. `STSLoadWorker` validates and upgrades the user-selected STS file.
3. Only after worker success does `MainWindow._on_sts_load_finished()` open the main-thread `STSStore`.
4. Only after the main store exists does `_start_sts_index_build()` create `STSIndexWorker`.

The gate is intentionally not placed in every `STSStore.__init__`, save worker, or index worker. Re-running full fingerprint/integrity scans for every worker-local store would duplicate migration ownership, add connection cost, and increase concurrency surface.

## Regression coverage

### `tests/test_sts_schema_upgrade.py`

Covers:

- exact v14 → v15 → v16 → v17 registry chain,
- verified backup creation,
- v16 → v17 single-step upgrade,
- contiguous migration registry,
- backup-creation fail-closed behavior,
- current-version no-op,
- future-schema rejection,
- validated rollback without copying a backup over the source,
- failure before `BEGIN IMMEDIATE` without restore,
- backup restore as rollback-validation fallback,
- unversioned legacy compatibility bootstrap.

### `tests/test_sts_schema_upgrade_gate.py`

Covers:

- fingerprint coverage from the registry floor through the current schema,
- realistic v14 and v16 physical schemas,
- source preflight and target postflight fingerprint checks,
- detection of a fake/mislabeled v14 database before backup or mutation,
- detection of a v17 label on a v16 physical schema,
- legacy-bootstrap output validation,
- future fingerprint contract fail-closed behavior,
- worker use of the guarded entrypoint.

### `tests/test_sts_schema_upgrade_orchestration.py`

Uses AST call-graph checks to lock the STS open ownership boundary without modifying `main_window.py`:

- `start_sts_load()` must create `STSLoadWorker`,
- `start_sts_load()` must not directly create `STSStore` or `STSIndexWorker`,
- `_on_sts_load_finished()` must create `STSStore` and start index building,
- `_start_sts_index_build()` must create `STSIndexWorker`,
- `STSLoadWorker` must call the fingerprint-gated upgrade entrypoint.

## CI validation evidence

A temporary branch-only PR workflow was used to validate the feature against a real GitHub repository checkout. It was removed after validation.

Final focused result:

- `20 passed in 0.59s`

The final CI also cloned and validated the exact source baseline:

- baseline SHA: `2931fa267560397d4d849d6365acde504f376775`
- feature SHA at validation: `ba2c521b656eddeb9ebec2fc8054f1de0826a904`

Baseline and feature full pytest suites were then executed in the same Ubuntu/Qt/Python environment and their JUnit failure node sets were compared.

Both full suites returned a non-zero status because the exact baseline already contained failures in that Linux/Qt environment. The comparison gate completed successfully and found no feature-only failing test names. The feature branch therefore introduced no new failing test node relative to its exact `main` baseline in that validation environment.

The validation-only draft PR `#308` was closed without merge.

## Deliberately untouched production areas

To keep future integration conflict surface low, this branch does not modify:

- `src/services/sts_database.py`
- `src/services/sts_store.py`
- `src/ui/main_window.py`
- contract detail UI modules
- share/merge domain or business services

The only pre-existing production file modified is `src/workers/sts_load_worker.py`.

## Future main integration rule

Do not blindly merge this branch into a later `main` after parallel development has continued.

At integration time:

1. Read the then-current `CURRENT_SCHEMA_VERSION` and the current schema tail in `STSDatabase.init_schema()`.
2. Compare any schema changes added after v17 with this branch's migration registry and fingerprint manifest.
3. Add explicit migration/fingerprint contracts for every newly introduced schema version before integration.
4. Re-check the current `STSLoadWorker` open boundary for parallel changes.
5. Run the focused schema/orchestration suite.
6. Run a baseline-vs-feature failure-set comparison against the then-current main, rather than relying on the July 10, 2026 baseline result.

This keeps the versioned upgrade engine compatible with schema work merged by other branches after the branch was created.
