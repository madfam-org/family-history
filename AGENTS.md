# AGENTS.md — family-history

> Last Updated: 2026-10-01

<!-- MADFAM-AGENTS-CANONICAL v1 -->

> **Boundary checkpoint (2026-10-01, platform ops):** public repository. Operational detail
> (cluster topology, secret paths, break-glass procedures, operator runbooks, people) lives in
> the private `internal-devops` repository and is only pointed to from here — the rules are the
> repo-boundary contract (internal-devops `docs/repo-boundary-contract.md`). Never copy that detail in.

This is the canonical instruction file for any agent or person working in this repository.
`CLAUDE.md` is a compatibility shim that points here; repo policy lives in this file only.

## What this repo is

`family-history` is a codename; the public brand is still pending. The product is a
Spanish-first, open-source family-history platform. Families build their tree from evidence
and keep their living memory in the same place: written stories, voice interviews with the
elders, photos and documents. It serves Mexican and binational families first. Licence:
AGPL-3.0-only. Built and operated by Innovaciones MADFAM S.A.S. de C.V. on the MADFAM ecosystem.

Status: **incubating**. [`docs/HONEST_STATUS.md`](./docs/HONEST_STATUS.md) says what works today
and what does not. Keep it true when you change behaviour.

## Doctrines

CI and review enforce these. A change that breaks one does not merge.

1. **Synthetic data only.** This repo never holds a real family, person, minor, CURP, RFC, real
   photo or real document. That covers fixtures, seeds, tests, screenshots, demos and docs.
   Generate data with `family_history.domain.synth.generate_family()` and draw every name from
   `family_history.domain.synth.synthetic_lexicon()` (data files in `family_history.domain.data`).
   CI enforces it with `scripts/check-synthetic-fixtures.py`.
2. **Living people are private by default.** Anyone not proven dead and born within the last 110
   years, or with no known birth date, is visible only inside their family space. Nothing about a
   living person is ever public.
3. **Evidence first.** Facts are assertions with provenance and citations. Conflicting facts
   coexist and one is preferred. AI may only *suggest*; a person accepts a suggestion with a
   citation.
4. **The exit is free.** Full export works at every tier, free included: GEDCOM 7 GEDZIP,
   GEDCOM 5.5.1 and the lossless native JSON.
5. **Consume the ecosystem; never rebuild it.** No LLM, payment or messaging provider key may
   ever live in this repo or its runtime config.

   | Capability | Owner |
   |---|---|
   | Identity, organizations, entitlements | Janua |
   | Billing and money | Dhanam |
   | LLMs | Selva, with `X-Sensitivity` `restricted` or `confidential` |
   | Document reading (OCR) | tlacuilo |
   | Generative media | ceq |
   | Third-party messaging | Angelia Courier |
   | QR codes and short links | marca |
   | Deploy | Enclii |
6. **Never:**
   - DNA or genetic data;
   - CURP collection;
   - health-risk inference;
   - data sale;
   - training models on family content;
   - voice cloning or face animation of real people.
7. **Language.** Code, identifiers, commits, PRs and engineering docs are in English. Everything
   a family reads is Spanish-first (es-MX), with English second.

## Operating doctrine

- **Enclii first.** Production operations go through Enclii's web UI, API or CLI. Raw cluster
  access is bootstrap or documented break-glass only, and break-glass procedures never live in
  this public repo.
- **Secrets** reach production only through `enclii secrets intake`. They never go in a manifest,
  commit, PR body, CI log or chat.
- **Credential files** (`.env*`, `~/.npmrc`, `~/.netrc`, kubeconfigs) are never printed. Check
  presence with counts only.
- **Commits.** Every agent commit carries the session's `Co-Authored-By` trailer.
- **PRs.** Agents prepare PRs and never merge their own.

## Layout

| Path | What lives there |
|---|---|
| `api/` | Python 3.12 service. Package `family_history`: API, worker, migrations, MCP |
| `api/src/family_history/domain/`, `api/src/family_history/gedcom/` | Pure genealogy library (no I/O): names, dates, kinship, privacy rules, GEDCOM 7 and 5.5.1, synthetic data |
| `apps/web/` | Next.js 16.3.8 app: the public landing and the signed-in app, routed by host |
| `packages/contracts/` | Generated OpenAPI and TS types, plus the export JSON Schema |
| `infra/`, `enclii.yaml`, `janua.client.yaml` | Deployment manifests (names only, never secret values) |
| `scripts/` | Repo guards run by CI |
| `docs/` | Architecture, privacy, status, ADRs (`docs/adr/`), per-lane build notes (`docs/lanes/`) |

## Interface contracts

[`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) §Contracts fixes the following:
- ports and health paths;
- environment variable names;
- image names and Dockerfile locations;
- hostnames;
- the v1 API surface the web app builds against.

Changing any of them needs an ADR in `docs/adr/`.

## Working here

**API.**
```bash
cd api
uv venv --python 3.12
uv pip install -e '.[dev]'
.venv/bin/ruff check . && .venv/bin/mypy src && .venv/bin/pytest -q
```

**Web,** once `apps/web` exists:
```bash
corepack enable
pnpm install --frozen-lockfile
pnpm --filter @family-history/web run lint
pnpm --filter @family-history/web run typecheck
pnpm --filter @family-history/web run test
pnpm --filter @family-history/web run build
```

**File size.** CI warns when a source file passes 600 lines and fails it past 800. Split modules
before they get there.

**Branches and PRs.** Feature branches only, English titles, CI green before review.

## What is not done

[`docs/HONEST_STATUS.md`](./docs/HONEST_STATUS.md) is the only list. Do not describe a planned
capability as shipped anywhere else: not in README, not in llms files, not in UI copy.
What comes next, and the dependency holds, are in [`docs/ROADMAP.md`](./docs/ROADMAP.md).
