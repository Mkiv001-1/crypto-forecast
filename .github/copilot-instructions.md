# Copilot Instructions for forecast

## Source of Truth and Sync Policy
- Source of truth: .windsurf/rules/content.md
- Last sync date: 2026-05-11
- If this file conflicts with .windsurf/rules/content.md, follow .windsurf/rules/content.md and update this file.
- When .windsurf/rules/content.md changes, update this file in the same change set.

## Project Context
- Stack: PyQt6 GUI + FastAPI, Python 3.12, SQLite WAL, OpenRouter AI.
- Domain flow: N models x M methods -> consensus -> bracket orders via IB Gateway.

## Standards
- Use Python 3.12 with type hints and PEP8 style.
- Do not add new dependencies without clear justification.
- Prefer small, named functions.
- Warn before API changes.

## Architecture Constraints
- Keep layering as Core -> Server -> Client.
- Do not add new architectural layers without strong need.
- For new features, create docs/features/<name>.md first, then implement code.

## Testing Requirements
- Use pytest.
- Keep tests deterministic.
- Use explicit error handling.

## Response Preferences
- Respond in Russian text.
- Keep code and identifiers in English.
- Prefer concise structure:
  1) 2-5 bullet overview
  2) Code blocks with file paths and only relevant parts
  3) Remaining tasks (if any)

## Avoid Without Discussion
- Rewriting scripts/core/forecast_runner.py, scripts/core/consensus.py, scripts/core/order_manager.py.
- SQLite schema/data changes without scripts/core/migrate.py updates.
- Raw SQL outside scripts/core/sqlite_manager.py.
- Changing consensus/EMA weights.