---
name: full-check
description: Run the MagicbHAnds /regression and /walkthrough together, end to end - every regression stage with firmware compiles, the walkthrough crawl, all five reviewers at once (bugs, security claims, outsider attack, desktop, phone) - and give the owner one summary with both report links. Use for "/full-check" or "check everything".
---

# Full check: regression and walkthrough together

This runs the two other skills in one go. Follow their steps; this file only
says how they fit together. Like them, it **fixes nothing in product code**.

`/full-check` is always end to end: every stage, `--compile`, the **full**
security and bug review (not scoped to the changes), and the walkthrough.

1. **Bring the suite up to date**: `/regression` step 1 (catalogue, checks,
   manual list). Commit.
2. **Start everything at once**:
   - the stages and the walkthrough in one runner call (they write to separate
     directories, `regression/out/` and `regression/walkthrough/out/`, and use
     separate mock hosts and browsers, so they can't collide):

     ```
     HA_PYTHON=... ESPHOME_PYTHON=... HA_URL=... python3 regression/run.py --compile --with-walkthrough
     ```
   - the three regression reviewers (`/regression` step 3: bugs, security
     claims, outsider attack), in the background, with the full scope;
   - the two walkthrough reviewers (`/walkthrough` step 2) once the crawl has
     written its inventory and screenshots (about a minute in).
   Five reviewers in all, each fresh and independent, each briefed with the
   code and evidence rather than conclusions.
3. **Reports**: `/regression` step 4 and `/walkthrough` step 3: both
   `notes.json` files, both reports built, both published privately to their
   usual URLs, the `RUNS.md` and `WALKTHROUGHS.md` entries.
4. **Commit** the suite changes and both log entries; PR as usual.
5. **One summary for the owner**, short:
   - regression totals (pass, fail, manual, skip) and the failing IDs, in a
     sentence each;
   - security and bug findings by severity, with the one or two that matter;
   - walkthrough findings by group (merge, rename, move, remove, flow, mobile,
     keep separate), with the top few;
   - what couldn't run here and why (no device attached, a site blocked from
     the sandbox, no Home Assistant reachable);
   - both report links, and how long it took.
