# HOTFIX — Share Assignment Merge + Merge UX + Label Policy

## Serial/queue root cause

Kuyruk no / seri no data is persisted in the STS/share database, but it was not part of the canonical contract snapshot used by the share three-way merge pipeline.

Production call-chain:

1. `DeliveryDialog` stores left-panel assignment rows in `DeliveryInfo.component_units`.
2. `STSStore.write_contract()` writes those rows to `delivery_component_units` keyed by `delivery_component_id + slot_no`.
3. `STSStore.load_contract_structure()` reads `delivery_component_units` back into `DeliveryInfo.component_units`.
4. `build_contract_snapshot()` previously serialized delivery components with only `name/planned/delivered`.
5. `build_merge_plan()` therefore never saw assignment add/update/delete and `apply_resolved_share_merge()` never received an operation for unit rows.

## DB persistence result

DB persistence is valid. Real table and relationship:

- table: `delivery_component_units`
- PK: local SQLite `id` only, not cross-file stable
- stable merge identity: parent delivery `merge_uid` + canonical component `name` + `slot_no`
- relationship: `delivery_component_units.delivery_component_id -> delivery_components.id -> deliveries.id`
- fields: `slot_no`, `identifier` (serial/queue value), `is_delivered`, `note`
- save writer: `STSStore.write_contract()`
- load reader: `STSStore.load_contract_structure()`

## Snapshot/diff/apply gap

The gap was snapshot/diff/apply coverage, not initial persistence:

- snapshot reader did not include `delivery_component_units` under delivery component snapshots;
- merge diff only compared delivery component `planned/delivered` fields;
- apply writer only updated delivery component quantities.

## Assignment identity decision

No local SQLite integer id is used cross-file. Assignment rows are represented as component `units` under the canonical delivery component relation:

`delivery.merge_uid / component.name / slot_no`

This follows existing delivery component identity and makes source/share rematerialized integer IDs irrelevant.

## Merge support summary

The canonical snapshot now includes component `units`, and delivery component diff compares `planned`, `delivered`, and `units` deterministically. Applying a remote `units` operation replaces the target component's unit rows for that delivery/component with the normalized remote slot list.

Covered changes:

- assignment add
- serial/queue update through `identifier`
- queue/note update through `note`
- assignment remove
- conflict/local keep/remote take/skip behavior for divergent unit lists
- deterministic operation hashes

## Merge dialog style fix

`ShareMergeDialog` now sets a dialog object name and uses dialog-scoped selectors for summary/value/title labels. Detail/value labels are transparent inside the dialog instead of inheriting unrelated global gray label fills.

## JSON formatter/presenter

Merge detail tooltips now use a user-facing formatter instead of raw JSON dumps. Delivery/component/unit details are shown with semantic labels and hide raw `merge_uid`, `payload_json`, ids and hashes.

## Label share policy

Share mode no longer supports label mutation. The scoped share capability allowlist no longer includes `manage_labels`, and ContractWorkWindow disables tag add/remove actions in both VIEW and EDIT shares with the policy message:

`Etiket işlemleri paylaşım dosyasında desteklenmez. Ana STS dosyasında yapılmalıdır.`

Normal STS label behavior is unchanged. No tag catalog is copied into share files.

## Tests

Added/focused coverage for:

- share DB close/reopen serial persistence;
- share DB close/reopen queue/note persistence;
- remote-only assignment add merge;
- remote-only serial update merge;
- remote-only queue update merge;
- remote-only assignment delete merge;
- assignment conflict with LOCAL_KEEP / REMOTE_USE / SKIP;
- operation hash determinism;
- raw JSON-free detail formatting;
- share EDIT label capability denial;
- existing scoped permission and core merge regressions.

## Qt skip

Linux full pytest continues to skip three Qt runtime tests because `libGL.so.1` is unavailable. The new assignment merge, presenter, and label policy tests are Qt-independent.

## Windows retest list

- In an EDIT share, enter serial/queue values in delivery component assignment panel, close/reopen the share, and verify values persist.
- Merge the edited share into source STS and verify serial/queue rows appear in the source delivery component.
- Change an existing serial/queue value in share and verify merge updates the source.
- Delete/clear assignment rows in share and verify merge removes the source rows when remote is selected.
- Create a local/source vs share assignment conflict and verify Local Keep, Remote Take, and Skip behavior.
- Open Share Merge dialog and verify detail/value text does not have gray rectangular artifacts.
- Hover/read change details and verify no raw JSON/dict/payload/hash/merge_uid appears.
- In share VIEW and EDIT, verify tag add/remove/assign actions are disabled and show the share-label policy message.
- Re-check scoped edit actions: Ana Bilgileri Düzenle, Sistem Ekle/Düzenle, Teslimat Ekle/Düzenle, Otomatik Teslimat Oluştur.
