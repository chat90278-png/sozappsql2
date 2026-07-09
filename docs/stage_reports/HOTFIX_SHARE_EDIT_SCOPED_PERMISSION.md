# HOTFIX — Share Edit Scoped Permission

## Root cause

`ContractWorkWindow.require_permission_ui()` called `has_permission("edit_contracts")` for save and mutation flows. In share runtime the synthetic share actor has no `staff` row in the share database. Because `ContractWorkWindow.has_permission()` passed the share DB connection to `auth.has_permission()`, the role lookup queried `staff.id=0`, found no row, and returned false before dialogs such as **Sistemi Düzenle** could open.

## Exact failing guard

`Sistemi Düzenle` call chain:

1. `ContractWorkWindow.edit_system()` checks share view-only mode.
2. The user edits the system table/dialog and later saves.
3. `ContractWorkWindow.save_all()` calls `require_permission_ui("edit_contracts", "Sözleşme Kaydet")`.
4. `ContractWorkWindow.has_permission()` delegated to `auth.has_permission(current_staff, "edit_contracts", share_db_conn)`.
5. The share DB has empty `staff`/`system_admins`, so `auth.has_permission()` denied with `Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.`

## Scoped capability semantics

A centralized share capability now grants mutation only when all are true:

- share mode is active;
- permission mode is `edit`;
- share metadata is present and well-formed;
- metadata `source_contract_merge_uid` matches the currently targeted contract `merge_uid`;
- the requested operation is in the contract-scoped allowlist.

Malformed or missing metadata fails closed.

## Allowed / denied matrix

| Context | Contract main edit | System edit | Delivery/term edit | Tags | Create/delete contract | Staff/admin/SQL/global platform-component |
|---|---:|---:|---:|---:|---:|---:|
| Normal STS | Existing role/admin system | Existing role/admin system | Existing role/admin system | Existing role/admin system | Existing role/admin system | Existing role/admin system |
| Share VIEW | Denied | Denied | Denied | Denied | Denied | Denied |
| Share EDIT, matching contract | Allowed | Allowed | Allowed | Allowed | Denied | Denied |
| Share EDIT, wrong/missing contract metadata | Denied | Denied | Denied | Denied | Denied | Denied |

## Production patch

- Added `src/share_permissions.py` for centralized scoped share authorization.
- Wired `ContractWorkWindow.has_permission()` through the scoped capability before falling back to normal STS authorization.
- Removed broad synthetic share-user edit permissions from share window creation.
- Added `src/contract_projection.py` so system/component table projection uses canonical component names instead of local integer ids.

## Tests

Added Qt-independent tests for:

- normal STS not being bypassed;
- VIEW share denial;
- EDIT share contract-scoped allowlist;
- wrong contract denial;
- create/delete/global/admin/SQL denial;
- missing/malformed metadata fail-closed;
- share projection preserving `Sistem 1` `Hava Aracı=3`, `YKİ=2`, `YVT=2` and `Sistem 2` `2/1/1` by component name.

## Qt skip status

The new authorization/projection coverage is Qt-independent. Full pytest may still skip Qt UI tests on Linux hosts that lack display/libGL runtime support.

## Windows retest actions

Retest these buttons/actions against the uploaded edit share:

- Ana Bilgileri Düzenle
- Sistem ekle
- Sistemi Düzenle
- Teslimat ekle/düzenle
- Otomatik Teslimat Oluştur
- contract-scoped tag/document mutation
- create/delete contract remains unavailable
- staff/admin, SQL/terminal, platform/component management remain unavailable
- Sistem 1 projection shows Hava Aracı=3, YKİ=2, YVT=2 before saving
