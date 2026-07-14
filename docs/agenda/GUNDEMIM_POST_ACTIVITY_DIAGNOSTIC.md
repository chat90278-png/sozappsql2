# Gündemim Post-Activity Diagnostic

- target_base_head: `87c2b07985c3c0854d197b0950d9243b9817877e`
- source_head: `66681d51877ad09db7379b6bbd7049a7436af1fc`
- resolve: `failure`
- install: `skipped`
- compile: `skipped`
- targeted: `skipped`

## resolve log tail
```text
From https://github.com/chat90278-png/sozappsql2
 * branch            integration/gundemim-current-main-20260713 -> FETCH_HEAD
 * branch            integration/gundemim-after-activity-20260714 -> FETCH_HEAD
Auto-merging src/services/sts_database.py
CONFLICT (content): Merge conflict in src/services/sts_database.py
Auto-merging src/services/sts_schema_upgrade.py
CONFLICT (content): Merge conflict in src/services/sts_schema_upgrade.py
Auto-merging src/services/sts_schema_upgrade_gate.py
CONFLICT (content): Merge conflict in src/services/sts_schema_upgrade_gate.py
Auto-merging tests/test_sts_schema_upgrade.py
CONFLICT (content): Merge conflict in tests/test_sts_schema_upgrade.py
Auto-merging tests/test_sts_schema_upgrade_gate.py
CONFLICT (content): Merge conflict in tests/test_sts_schema_upgrade_gate.py
Automatic merge failed; fix conflicts and then commit the result.
Traceback (most recent call last):
  File "D:\a\sozappsql2\sozappsql2\tools\validation\gundemim_post_activity_resolve.py", line 262, in <module>
    main()
  File "D:\a\sozappsql2\sozappsql2\tools\validation\gundemim_post_activity_resolve.py", line 258, in main
    verify_contract()
  File "D:\a\sozappsql2\sozappsql2\tools\validation\gundemim_post_activity_resolve.py", line 233, in verify_contract
    raise RuntimeError("Stale Agenda v18 expectations:\n" + "\n".join(stale_hits))
RuntimeError: Stale Agenda v18 expectations:
tests\test_activity_history_main_integration.py:CURRENT_SCHEMA_VERSION == 18
tests\test_activity_history_operations.py:CURRENT_SCHEMA_VERSION == 18
tests\test_activity_history_query.py:CURRENT_SCHEMA_VERSION == 18
```

## install log tail
```text
(no log)
```

## compile log tail
```text
(no log)
```

## targeted log tail
```text
(no log)
```
