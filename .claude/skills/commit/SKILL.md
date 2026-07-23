---
name: commit
description: Use when the user asks to commit changes (e.g. "commit this", "make a commit", "/commit"). Stages the relevant files and writes a Conventional Commits message matching this repo's pr-title-lint.yml / cliff.toml rules, since PR titles get squash-merged into main and are what auto-release.yml parses for the changelog and version bump.
---

# Commit

Write commit messages in this repo as Conventional Commits — not as a style
preference, but because `.github/workflows/pr-title-lint.yml` enforces this
format on PR titles, and PRs are squash-merged, so the PR title becomes the
commit message `git-cliff` reads on release (see `cliff.toml`) to generate
`CHANGELOG.md` and pick the version bump. Keeping every commit in this format
also avoids the "single-commit PR" trap, where GitHub defaults the squash
commit message to that one commit's message instead of the PR title.

## Steps

1. Run `git status` and `git diff` (staged + unstaged) to see what actually
   changed. Never guess from memory of earlier edits in the conversation.
2. Stage specific files by name (`git add <file> <file>`) — never `git add -A`
   or `git add .`. If a broad add already happened, review `git status` before
   committing and double-check file contents if anything looks like it could
   hold a secret.
3. Pick exactly one type for the subject line:

   | Type       | Use for                                             |
   |------------|------------------------------------------------------|
   | `feat`     | a new user-facing capability                          |
   | `fix`      | a bug fix                                             |
   | `perf`     | a performance improvement                             |
   | `refactor` | internal restructuring, no behavior change            |
   | `docs`     | documentation only                                    |
   | `chore`    | tooling, deps, config, maintenance                    |
   | `ci`       | CI/workflow changes                                   |
   | `test`     | tests only                                             |

   Add a scope in parens if it clarifies where the change is
   (`feat(sidepanel):`, `fix(server):`) — optional, not required
   (`requireScope: false`).

4. If the change breaks an existing API/contract/behavior, mark it explicitly:
   either `!` right after the type/scope (`feat!:`, `fix(server)!:`) or a
   `BREAKING CHANGE: <explanation>` footer. This is what makes `git-cliff` cut
   a major version bump — don't add it casually.
5. Write the subject imperative, present tense, no trailing period, short
   enough to read as a PR title (aim for under ~70 chars). Add a body only if
   the *why* isn't obvious from the diff — skip a body that just restates the
   diff.
6. Commit via heredoc so formatting survives, e.g.:
   ```bash
   git commit -m "$(cat <<'EOF'
   fix(apiClient): retry job-session fetch on transient 502

   Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
   EOF
   )"
   ```
7. Run `git status` after to confirm the commit landed and nothing unstaged
   was left behind unintentionally.

## Notes

- `chore:`/`ci:`/`test:` commits are valid and expected — they just don't
  show up in `CHANGELOG.md` and don't by themselves trigger a release (see
  `cliff.toml`'s `commit_parsers`). If every commit since the last tag is one
  of these, `auto-release.yml` correctly cuts no release — that's by design,
  not a bug to work around.
- Never amend, force-push, or skip hooks (`--no-verify` etc.) unless the user
  explicitly asks — this skill only changes *what the message says*, not the
  general git safety rules already in force for this session.
- This only governs the commit message itself. If the change is going into a
  PR, the **PR title** is what actually matters for the changelog/version bump
  after squash-merge — keep it in the same format.
