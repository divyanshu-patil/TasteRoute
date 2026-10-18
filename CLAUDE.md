# CLAUDE.md

Follow `AGENTS.md` (all rules apply). Claude Code specifics:

- Start each session by reading `AGENTS.md`, `docs/progress.md` and the current phase in `docs/11-plan.md`.
- Use a task list per phase; mark a task complete only when its acceptance IDs pass and are recorded in `docs/progress.md`.
- Make small, reviewable changes. Run `pnpm turbo lint test` (and `uv run pytest -m "not live"` in `apps/api`) before saying a task is done. Report failures honestly.
- Never run live Qloo, Hunter, Overpass, Nominatim or Ollama calls in tests. Live calls only through the scripts in `apps/api/scripts/`, and say how many calls you spent.
- Never print, log or commit secrets. Do not read `.env` values aloud in chat.
- Do not edit generated files in `packages/contracts`; regenerate them.
- Do not change migrations that have been applied; add a new migration.
- When blocked (missing key, missing `DESIGN.md`, ambiguous Qloo behaviour), stop and ask with a short list of options.
- Summarise each phase in under 10 lines: what works, which IDs pass, what's next, anything needed from the user.
