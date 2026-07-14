# Current Schema Gate Test Conflict

## Region 1
```text
0228: 
0229:     with pytest.raises(STSMigrationError) as exc_info:
0230:         gate.upgrade_sts_file(path)
0231: 
0232:     error = exc_info.value
0233:     assert "şema sürümü ile gerçek veri yapısı uyuşmuyor" in error.user_message
0234:     assert "schema_fingerprint_mismatch=v14" in error.technical_detail
0235:     assert "missing_table:sts_metadata" in error.technical_detail
0236:     assert read_sts_schema_version(path) == 14
0237:     assert not (tmp_path / "yedekler").exists()
0238: 
0239: 
0240: <<<<<<< HEAD
0241: def test_current_v19_with_v16_shape_is_rejected_instead_of_silent_noop(
0242: =======
0243: def test_current_v18_with_v16_shape_is_rejected_instead_of_silent_noop(
0244: >>>>>>> origin/integration/gundemim-current-main-20260713
0245:     tmp_path: Path,
0246: ):
0247:     path = tmp_path / "drifted-current.sts"
0248:     _make_historical_database(path, 16)
0249:     conn = sqlite3.connect(path)
0250:     try:
0251:         _set_schema_version(conn, CURRENT_SCHEMA_VERSION)
0252:         conn.commit()
0253:     finally:
0254:         conn.close()
0255: 
0256:     with pytest.raises(STSMigrationError) as exc_info:
```
## Region 2
```text
0249:     conn = sqlite3.connect(path)
0250:     try:
0251:         _set_schema_version(conn, CURRENT_SCHEMA_VERSION)
0252:         conn.commit()
0253:     finally:
0254:         conn.close()
0255: 
0256:     with pytest.raises(STSMigrationError) as exc_info:
0257:         gate.upgrade_sts_file(path)
0258: 
0259:     error = exc_info.value
0260:     assert "şema sürümü ile gerçek veri yapısı uyuşmuyor" in error.user_message
0261: <<<<<<< HEAD
0262:     assert "schema_fingerprint_mismatch=v19" in error.technical_detail
0263: =======
0264:     assert "schema_fingerprint_mismatch=v18" in error.technical_detail
0265: >>>>>>> origin/integration/gundemim-current-main-20260713
0266:     assert "missing_column:share_packages.cancelled_at" in error.technical_detail
0267:     assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION
0268:     assert not (tmp_path / "yedekler").exists()
0269: 
0270: 
0271: def test_v16_upgrade_is_postflight_validated_as_current_schema(tmp_path: Path):
0272:     path = tmp_path / "realistic-v16.sts"
0273:     _make_historical_database(path, 16)
0274: 
0275:     result = gate.upgrade_sts_file(path)
0276: 
0277:     assert result.applied_migrations == (
```
## Region 3
```text
0267:     assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION
0268:     assert not (tmp_path / "yedekler").exists()
0269: 
0270: 
0271: def test_v16_upgrade_is_postflight_validated_as_current_schema(tmp_path: Path):
0272:     path = tmp_path / "realistic-v16.sts"
0273:     _make_historical_database(path, 16)
0274: 
0275:     result = gate.upgrade_sts_file(path)
0276: 
0277:     assert result.applied_migrations == (
0278:         "v16_to_v17_share_cancellation_audit",
0279: <<<<<<< HEAD
0280:         "v17_to_v18_activity_history_infrastructure",
0281: =======
0282:         "v17_to_v18_staff_agenda_state",
0283: >>>>>>> origin/integration/gundemim-current-main-20260713
0284:     )
0285:     assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION
0286:     assert (
0287:         gate.validate_versioned_schema_fingerprint(
0288:             path,
0289:             CURRENT_SCHEMA_VERSION,
0290:         ).version
0291:         == CURRENT_SCHEMA_VERSION
0292:     )
0293: 
0294: 
0295: def test_legacy_bootstrap_output_must_pass_current_fingerprint(tmp_path: Path):
```
## Region 4
```text
0318:     db = STSDatabase(path)
0319:     db.close()
0320: 
0321:     monkeypatch.setattr(gate, "FINGERPRINT_VERSIONS", (14, 15, 16))
0322: 
0323:     with pytest.raises(STSMigrationError) as exc_info:
0324:         gate.validate_versioned_schema_fingerprint(
0325:             path,
0326:             CURRENT_SCHEMA_VERSION,
0327:         )
0328: 
0329:     assert "şema doğrulama sözleşmesi kayıtlı değil" in exc_info.value.user_message
0330: <<<<<<< HEAD
0331:     assert "schema_fingerprint_not_registered=v19" in exc_info.value.technical_detail
0332: =======
0333:     assert "schema_fingerprint_not_registered=v18" in exc_info.value.technical_detail
0334: >>>>>>> origin/integration/gundemim-current-main-20260713
0335: 
0336: 
0337: def test_sts_load_worker_uses_schema_upgrade_gate_entrypoint():
0338:     source = Path("src/workers/sts_load_worker.py").read_text(encoding="utf-8")
0339: 
0340:     assert (
0341:         "from src.services.sts_schema_upgrade_gate import upgrade_sts_file"
0342:         in source
0343:     )
0344:     assert (
0345:         "from src.services.sts_schema_upgrade import upgrade_sts_file"
0346:         not in source
```
