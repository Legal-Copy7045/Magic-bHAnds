# Regression runs

One entry per full run (newest first): version, totals, failing check IDs, finding IDs, report link.
No real names, hosts or device IDs: this file is public.

## 2026-11-26 — 0.10.37 at 690a610 (first /full-check; review: full)

- Totals: 704 pass, 1 fail, 19 manual, 3 skip (727 checks; 164 features catalogued). Stages ran side by side in 1 min 45 s;
  about 15 minutes in all with the five reviewers.
- Stages: integration 246/0, ci 61/0, firmware 162/0 (+19 manual, every build compiled), page 185/0, live 34/0 (+3 skip),
  quality 10/1, ID registry 7/0.
- Failing checks: QUAL-006 (fonttools 4.60.1 in CI's font test has CVE-2025-66034; not exploitable here, 4.60.2 fixes it).
- Findings (all low or info): BUG-031..037 (5 low, 2 info), SEC-024..029 (3 low, 3 info), ATK-001..004 (2 low, 2 info).
  BUG-036 = SEC-028 = ATK-001; SEC-025 = ATK-002. docs/security.md: 77 claims checked, 3 don't hold (SEC-024, SEC-026, SEC-027).
- Report: https://claude.ai/artifact/XZLBtezEhawCL1am8XatZY (private, updated in place)

## 2026-11-24 — 0.10.37 (clean, after five fix rounds)

- Totals: 684 pass, 0 fail, 19 manual, 3 skip (706 checks; 157 features catalogued).
- Stages: integration 246/0, ci 57/0, firmware 162/0 (+19 manual, every build compiled), page 185/0,
  live 34/0 (+3 skip: GitHub Pages not reachable from the sandbox; release files checked instead).
- Failing checks: none.
- Findings: none open. Fixed since the first run: SEC-001..023 and BUG-001..030 as reviewed in rounds 1-5
  (0.10.32 to 0.10.37); round 5's BUG-028, BUG-029, BUG-030 and SEC-023 fixed in 0.10.37.
- Report: https://claude.ai/artifact/XZLBtezEhawCL1am8XatZY (private, updated in place)

## 2026-11-24 — 0.10.31 (first run)

- Totals: 558 pass, 13 fail, 13 manual, 4 skip (584 automated checks; 123 features catalogued).
- Stages: integration 194/3, ci 39/1, firmware 127/3 (+13 manual), page 168/5, live 30/1 (+4 skip).
- Failing checks: INT-098, INT-105, INT-106, CI-037, FW-107, FW-113, FW-166, PAGE-072, PAGE-122, PAGE-132,
  PAGE-166, PAGE-173, LIVE-028.
- Findings: SEC-001..013 (4 medium, 5 low, 4 info), BUG-001..012 (1 high, 1 medium, 8 low, 2 info).
  docs/security.md: 38 claims checked, 5 don't hold (SEC-001, SEC-002, SEC-004, SEC-005, SEC-013).
- Report: https://claude.ai/artifact/XZLBtezEhawCL1am8XatZY (private)
