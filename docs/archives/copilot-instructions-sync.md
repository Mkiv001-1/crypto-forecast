# Copilot Instructions Synchronization

## Goal
Keep GitHub Copilot instructions aligned with the Windsurf source rules.

## Source of Truth
- Primary file: .windsurf/rules/content.md
- Synced file: .github/copilot-instructions.md
- Optional global profile file: c:/Users/ivano/AppData/Roaming/Code/User/prompts/forecast-global.instructions.md

## Update Process
1. Edit .windsurf/rules/content.md first.
2. Update .github/copilot-instructions.md in the same change.
3. Update global profile instructions only for generic cross-project rules.
4. Do not copy forecast-specific architecture restrictions into global instructions.
5. In PR description, note that instructions were synchronized.

## Validation Checklist
- Copilot references .windsurf/rules/content.md as source of truth.
- Repo-level instructions still include standards, architecture constraints, testing, and avoid rules.
- Global instructions remain generic and safe for other repositories.

## Notes
- If guidance conflicts, prefer direct user request first, then repository source rules.
- Keep instructions short to avoid wasting context window.