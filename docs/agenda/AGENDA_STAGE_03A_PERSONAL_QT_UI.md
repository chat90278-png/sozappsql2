# Gündemim Stage 3A Personal Qt UI

## Scope

Stage 3A connects the runtime-accepted personal Agenda application layer to the existing Qt main page on `feature/gundemim-agenda-system`.

Implemented UI scope:

- 112 px compact `GÜNDEMİM` header card;
- compact rendering of `AgendaPresentationSnapshot.compact_items`;
- non-modal `Qt.Tool` detail window rendering `detail_items`;
- 650 ms engagement dwell before seen requests;
- condition snooze presets;
- existing contract navigation delegation;
- loading, error and empty states;
- debounced agenda refresh and STS-store rebinding;
- source and offscreen Qt test coverage.

No provider, lifecycle, schema, transaction, state SQL or permission model was changed.

## Accepted Baseline

Runtime-accepted Stage 2B head:

`0088006620c25a2508cbc3b7885d173bb5662292`

The Stage 2B validation gate accepted the context factory, presentation projection and personal facade on the isolated feature branch. Main merge remains closed.

## Exact Insertion Point

The existing compact header is owned by `src/ui/main_page_final_window.py` and composed as:

`BUGÜN → upcoming area → TAKVİM`

The Analysis Center layer already removes the upcoming scroll and inserts `ContractStatusSummaryWidget`, followed by a stretch before the existing calendar.

Stage 3A preserves the 146 px header container and replaces that stretch with `AgendaCompactWidget`, producing:

`BUGÜN → SÖZLEŞME DURUMU → GÜNDEMİM → TAKVİM`

The status widget and calendar retain their existing ownership and behavior.

## Ownership and Facade Wiring

`src/ui/main_page_analysis_window.py` owns:

- one `AgendaCompactWidget`;
- one `PersonalAgendaFacade` bound to the exact current `self.store.db`;
- one lazily created `AgendaDetailWindow`;
- one 200 ms single-shot refresh debounce timer.

The UI does not create SQLite connections. A changed STS store/DB identity invalidates the old facade, closes the detail window and creates a new facade only when the next authorized load occurs.

`self.current_staff` is passed unchanged to the facade.

## Compact Widget Contract

`src/ui/agenda_compact_widget.py` provides `AgendaCompactWidget(QWidget)`.

Contract:

- object name `AgendaCompactWidget`;
- fixed height 112 px;
- existing white-card, blue-gray border and radius language;
- local scoped stylesheet;
- snapshot order preserved;
- maximum two rows from `snapshot.compact_items`;
- NEW or active count summary;
- safe remaining-day/effective-date label;
- exact empty text `Şu anda gündeminiz temiz.`;
- non-blocking `Yükleniyor…` and `Gündem yüklenemedi` states;
- `Tümünü Gör` signal without opening a modal itself;
- contract navigation signal carrying only a positive contract ID.

Severity colors:

- CRITICAL `#DC2626`
- ATTENTION `#F59E0B`
- INFO `#2563EB`
- reserved SUCCESS `#16A34A`

## Detail Tool Window Contract

`src/ui/agenda_detail_window.py` provides `AgendaDetailWindow(QWidget)`.

The window:

- uses `Qt.Tool`;
- is non-modal;
- is parented to the main window;
- uses `WA_DeleteOnClose`;
- is lazily created and never duplicated;
- renders only `snapshot.detail_items`;
- preserves projection order and the 20-item projection limit;
- keeps seen condition items visible;
- shows active/new/snoozed summary counts;
- hides developer-only filtered terminology;
- provides `Sözleşmeyi Aç` and condition-only `Ertele` actions;
- constrains initial placement to the available screen;
- cancels pending dwell timers on hide/close.

## Seen Dwell Behavior

Loading a snapshot never marks items as seen.

Compact and detail row engagement use a 650 ms single-shot timer:

1. row selection/focus starts the timer;
2. changing selection cancels the previous timer;
3. hide, clear or close cancels the timer;
4. the same agenda key/version is emitted at most once per widget instance;
5. the exact `AgendaItem` is sent to the owner;
6. the owner calls `PersonalAgendaFacade.mark_seen(current_staff, item)`;
7. successful persistence triggers a snapshot reload;
8. no local fake-seen state is applied.

A seen condition remains visible; only the NEW state changes through the existing lifecycle engine.

## Snooze Presets

Only `CONDITION` items with `supports_snooze=True` expose snooze actions.

Stable preset codes:

- `tomorrow` — Yarın
- `three_days` — 3 Gün
- `one_week` — 1 Hafta

The UI does not calculate dates. The main-page owner calls `facade.snooze_until_for_preset(...)` and then `facade.snooze(...)`.

EVENT items have no snooze control. Permanent dismiss and custom snooze date are outside Stage 3A.

## Contract Navigation

Agenda navigation searches the already loaded `contract_index` for the requested stable contract ID and delegates the existing item dictionary to:

`open_contract_item(item)`

No alternate `ContractWorkWindow` creation path, SQL query or editor flow was introduced. `src/ui/main_window.py` did not require modification.

## Loading, Error and Empty Behavior

Permission behavior:

- without `view_contracts`, the compact widget is hidden;
- the detail window is closed;
- facade load and state interaction are not called.

Refresh behavior:

- `update_alert_strip()` schedules one debounced agenda refresh;
- repeated refresh bursts collapse through a 200 ms single-shot timer;
- post-seen and post-snooze refreshes run immediately;
- exceptions are logged through the existing module logger;
- compact/detail surfaces show safe error text;
- raw traceback text is not shown to the user.

STS switch behavior:

- `start_sts_load()` clears the old facade binding and snapshot;
- closes the old detail window;
- the next successful index/update hook binds to the new exact `store.db`.

## Style and Palette

The UI follows the current compact main page:

- page background `#e8eef5`;
- white cards;
- border family `#d7e0ea` / `#d8e2ed`;
- compact radius 12–15 px;
- blue interaction accent;
- dense typography sized to avoid clipping at Windows scaling;
- no dark popup card;
- no global stylesheet mutation;
- no absolute row coordinates.

## Tests

Added:

- `tests/test_agenda_compact_widget.py`
- `tests/test_agenda_detail_window.py`
- `tests/test_main_page_agenda_integration.py`

Coverage includes fixed height, empty/loading/error states, snapshot ordering, severity/date rendering, signals, 650 ms dwell and cancellation, non-modal tool flags, snooze visibility/preset codes, single-instance ownership, permission short-circuit, facade interactions, refresh debounce, STS rebinding, navigation delegation and absence of raw SQL.

## Exclusions

Not implemented in Stage 3A:

- Activity provider;
- Share provider;
- DocumentLock provider;
- manager/admin/viewer-specific agenda scopes;
- custom snooze date;
- durable hidden snoozed-item management;
- permanent EVENT dismiss UI;
- main integration or merge.

`PersonalAgendaFacade.clear_snooze()` remains available for a future presentation source that can expose snoozed items without inventing hidden-state SQL in the UI.

## Current Main Drift and Schema Risk

Current main has advanced independently and contains the automatic STS schema upgrade engine. The isolated feature remains schema 18 while current main remains an integration risk until:

- explicit v17→v18 migration support;
- schema 18 fingerprint reconciliation;
- current-main-based integration work;
- final current-main differential validation.

## Main Merge Gate

CLOSED.

This handoff authorizes only Stage 3A-V runtime/offscreen visual validation and further isolated work after that gate. It does not authorize merging to main.
