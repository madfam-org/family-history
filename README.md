# family-history

> Boundary checkpoint (2026-10-01): public repository. Operational detail lives in MADFAM's
> private internal-devops repository under the repo-boundary contract; nothing here names
> infrastructure, secrets or people.

**La memoria de tu familia, en tu idioma y bajo tu control.**

`family-history` is the working codename of a Spanish-first, open-source family-history
platform. The public brand is still pending.

Families use it to:
- **build their tree from evidence:** sources, citations, and conflicting facts kept side by side;
- **keep their living memory:** stories, voice interviews with the elders, photos and documents.

It is designed first for Mexican and binational families:
- dual surnames and apodos;
- compadrazgo;
- parish and civil records;
- haciendas and ranchos;
- the history of migration north;
- Día de Muertos.

**Status: incubating.** The first build wave (genealogy library, GEDCOM engine, API, web app
shell, platform) is on `main`; nothing is deployed yet.
[docs/HONEST_STATUS.md](./docs/HONEST_STATUS.md) is the single source of truth for what works.

## Principles

- **Private by default.** Living people are only ever visible to their own family.
- **Evidence first.** Every fact can carry its source; AI only suggests.
- **Free exit.** Export everything (GEDCOM 7, GEDZIP, GEDCOM 5.5.1, native JSON) at any tier.
- **Never:** DNA, CURP collection, data sale, or voice/face cloning of real people.

## Repository

| Path | Contents |
|---|---|
| `api/` | Python 3.12 service: FastAPI API, worker, migrations, MCP server, and the pure genealogy library |
| `apps/web/` | Next.js app: the public landing and the signed-in app |
| `packages/contracts/` | Generated OpenAPI, TypeScript types, export schemas |
| `infra/`, `enclii.yaml` | Deployment manifests for the MADFAM platform (no secret values) |
| `docs/` | [Architecture and contracts](./docs/ARCHITECTURE.md), [privacy rules](./docs/PRIVACY.md), [ADRs](./docs/adr/) |

Contributors and coding agents start with [AGENTS.md](./AGENTS.md). Ecosystem roles are in
[ECOSYSTEM.md](./ECOSYSTEM.md).

## Development

```bash
cd api
uv venv --python 3.12
uv pip install -e '.[dev]'
.venv/bin/pytest -q
```

Use synthetic data only. Never commit a real family's information, photos or documents.

## Licence

Copyright (C) 2026 Innovaciones MADFAM S.A.S. de C.V., Cuernavaca, Morelos, México.

This program is free software. You can redistribute it and/or modify it under the terms of the
GNU Affero General Public License, version 3 only (AGPL-3.0-only); see [LICENSE](./LICENSE).
If you run a modified version as a network service, you must offer its source to its users
(AGPL §13).
