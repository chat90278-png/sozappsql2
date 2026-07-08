# STS RC Freeze Policy

## RC1 entry criteria

RC1 can start only after all of the following are true:

- Manual Windows AŞAMA 20 validation is PASS on a real Windows machine.
- Qt test modules run without skips.
- `STS.exe` build and startup validation are PASS.
- Windows icon and taskbar behavior are PASS.
- Windows file-handle validation is PASS.
- Five pilot scenarios are PASS:
  - normal merge
  - conflict
  - partial merge
  - cancel
  - parallel share
- Full `python -m pytest -q` is PASS.

## Freeze rules after RC freeze

After RC freeze, only release-blocking fixes are accepted:

- crash
- data loss
- migration
- permission/security
- incorrect merge
- release-blocking Windows runtime

The following are not accepted into RC1 after freeze:

- new feature work
- UI polish
- performance rewrites
- non-blocking refactors
- schema/lifecycle/core merge behavior changes without a release-blocking reason
