# AŞAMA 17 — Performance and Crash/Error Audit Report

- Baseline/final pytest: `110 passed, 3 skipped`
- Synthetic dataset: 100 contract, 2500 system, 10000 delivery, 502 share row

## Measurements

| Area | Result |
| --- | ---: |
| STS open | warm median 19.42 ms |
| Snapshot build | warm median 9.51 ms |
| Share create | 87.08 ms |
| Prepare | warm median 81.16 ms |
| Resolution items | warm median 0.17 ms |
| Presenter | warm median 0.05 ms |
| Apply | 79.71 ms |
| History 500 | 17.01 ms / 1 SQL |
| Active query | 3.24 ms / 1 SQL |
| Cancel | 0.47 ms / bounded 5 SQL |

## Findings

- N+1 issue: not found.
- Sensitive log/raw traceback issue: not proven.
- Production patch: not required.
- Decision: AŞAMA 17 PASS.
- Open blocker: AŞAMA 16 Windows/Qt validation remains blocked until a real Windows environment with working QtWidgets runtime is available.
