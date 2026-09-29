# Contributing

## Branching strategy

Trunk-based, matching the commit history already in this repo:

- `main` is always deployable. Every push to `main` triggers `.github/workflows/deploy.yml`.
- Work happens on short-lived branches off `main`: `feat/<short-description>` for
  new functionality, `fix/<short-description>` for bug fixes. Keep them small
  and merge within a few days — long-lived branches drift and produce painful
  conflicts.
- Open a pull request into `main`. `.github/workflows/ci.yml` must be green
  (backend pytest, frontend lint + build, cross-browser Playwright e2e)
  before merging.
- Commit messages follow the existing convention: `fix: …`, `feat: …`,
  `chore: …` — imperative mood, explaining *why* over *what*.
- Prefer a single focused commit per logical change over a pile of "wip"
  commits; squash on merge if your change accumulated fixups.

## Local development

See `README.md` for the backend/frontend quick-start. Run the test suites
before opening a PR:

```bash
cd backend && .venv/bin/pytest -q
cd frontend && pnpm lint && pnpm build && pnpm test:e2e
```

## Reporting bugs / proposing features

Open a GitHub issue with reproduction steps (bugs) or the problem you're
trying to solve (features) — see `docs/DEPLOYMENT.md` for known MVP
boundaries that might already cover what you're about to file.
