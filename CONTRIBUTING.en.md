# Contributing to StockLLM

[简体中文](CONTRIBUTING.md) | [English](CONTRIBUTING.en.md)

Changes should preserve source provenance, data freshness, historical time boundaries, model restrictions, and local storage behavior.

## Before You Start

- Search existing issues before opening a new one.
- Use an issue to discuss broad product changes, new providers, schema changes, or changes to research semantics before implementing them.
- Never include API keys, credential-store contents, private research history, or diagnostic exports in issues, logs, fixtures, or screenshots.
- Keep pull requests focused. Separate unrelated refactors from behavioral changes.

## Development Setup

Requirements are Python 3.12+, Node.js 20+, and pnpm 9+. On Windows PowerShell:

```powershell
git clone https://github.com/kevynf/stock-llm.git
cd stock-llm
.\scripts\bootstrap.ps1
```

Run the backend and frontend in separate terminals:

```powershell
.\scripts\dev-backend.ps1
.\scripts\dev-frontend.ps1
```

The application is served at <http://127.0.0.1:5173>; the OpenAPI UI is at <http://127.0.0.1:8768/docs>.

## Engineering Rules

- Keep eligibility, research checks, and rankings in the backend engine. The frontend renders API state and must not reimplement research logic.
- Preserve provider-level source, effective date, fetch time, and freshness metadata. Do not infer provenance from field names or values.
- Historical research must not consume information published after the requested date.
- Treat provider text and model output as untrusted. Model-selected stocks and evidence IDs must remain inside server-owned allow-lists.
- Demo fixtures require `STOCKLLM_ENABLE_DEMO=1` and must never become a production fallback.
- Store secrets through the system credential store. Do not write credentials to SQLite, logs, fixtures, or committed environment files.
- Use official shadcn/ui components and follow the [design system](docs/design-system.en.md) for shared UI behavior.

## Tests

Run the complete check before submitting a pull request:

```powershell
.\scripts\check.ps1
```

This runs the backend test suite and the frontend TypeScript production build. Tests must be deterministic and must not depend on live market-data or model services.

Add focused tests for behavior changes, especially provider normalization, historical cutoffs, evidence validation, database transactions, and API contracts. For UI changes, verify the affected workflow at the supported 1280×720 desktop baseline and check the browser console.

## Pull Requests

A pull request should include:

- a concise description of the user-visible or architectural change;
- the reason for the change and any trust-boundary implications;
- tests run and their results;
- screenshots for visible UI changes;
- migration or compatibility notes when stored data or API contracts change.

Do not commit generated installers, local databases, caches, real diagnostics, or credentials. Keep documentation in English and Simplified Chinese synchronized when a change affects both versions.

By contributing, you agree that your contribution is licensed under the repository's [MIT License](LICENSE).
