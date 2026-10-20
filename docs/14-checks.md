# 14. Checks

## Before every commit

- [ ] `uv run ruff check . && uv run ruff format --check .` (API)
- [ ] `uv run mypy src` (API)
- [ ] `uv run pytest -m "not live"` passes
- [ ] `pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test`
- [ ] If schemas changed: `uv run python scripts/export_openapi.py` and regenerate `packages/contracts`
- [ ] If the database changed: a new migration file exists; `supabase db reset` works locally
- [ ] No `.env`, keys or fixtures with keys staged (`git diff --cached | grep -iE "api[_-]?key|secret|bearer"` returns nothing meaningful)
- [ ] Commit message references acceptance IDs, for example `feat(api): baseline lift [RNK-02]`

## CI (GitHub Actions, on every push)

1. API job: install with `uv`, ruff, mypy, pytest (not live) with coverage, grep tests (LLM-01, CAT-01, EXP-04).
2. Web job: pnpm install, lint, typecheck, Vitest, `next build`.
3. Contracts job: regenerate `openapi.json` and `packages/contracts`; fail if there is a diff.
4. Secret scan (for example gitleaks).
5. Optional: Supabase migration check against a throwaway database.

## End of each phase

- [ ] All acceptance IDs for the phase pass and are recorded in `docs/progress.md`
- [ ] Qloo calls used so far this month noted in `docs/progress.md`
- [ ] Docs updated where behaviour differs from the plan; decision logged in `18-risks-and-decisions.md`
- [ ] Demo still works (sample run loads)

## Daily

- [ ] Check Qloo monthly usage (query in `16-runbook.md`); stay under 60% before Oct 27
- [ ] Check Hunter credits remaining
- [ ] Back up the demo run (export its rows) once seeded

## Pre-demo (before recording the video)

- [ ] Demo run reseeded with the final scoring version
- [ ] Cache warm for the demo brand and city (run once)
- [ ] Ollama Cloud responding; tool calling works (`/health` shows `tools_ok: true`)
- [ ] Kill-switch rehearsal done; key restored afterwards
- [ ] Browser zoom, window size and test data ready; notifications off
- [ ] Evaluation results ready to quote

## Pre-submit (Oct 29)

Hackathon requirements (from the official rules):
- [ ] Working software that integrates the Qloo API
- [ ] It functions as an agentic tool / uses an agent (F09), and the README says how
- [ ] Public repository (GitHub, GitLab or Bitbucket) with an open-source `LICENSE` file
- [ ] Link to a functional demo application; works logged out and free to test
- [ ] Text description of features and functionality
- [ ] Demo video, public, English or with English translation
- [ ] Project works as shown in the video and text
- [ ] If any pre-existing code was used, the submission explains what was built during the hackathon period

Quality:
- [ ] Every MVP acceptance criterion passes
- [ ] Clean clone test on a second machine or fresh container
- [ ] README: setup, architecture diagram, Qloo call chain, kill switch, evaluation results, limits
- [ ] `/health` green on the deployed API
- [ ] Secret scan clean; no keys in the web bundle
- [ ] `pip-audit` and `pnpm audit` reviewed
- [ ] Devpost fields filled in
- [ ] Submitted at least 24 hours before the deadline
