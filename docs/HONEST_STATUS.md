# Honest status

> Last Updated: 2026-10-01

This is the only list of what works. When behaviour changes, update this file in the same PR.

## 2026-10-01: first build wave (on `main`)

**Not running anywhere.** No host serves this project yet. Deployment waits on the platform's
onboarding steps; see [DEPLOYMENT.md](./DEPLOYMENT.md).

**Exists and is tested**

- **Genealogy domain library** (`family_history.domain`, standard library only):
  - GEDCOM 7 dates, with forgiving Spanish input («hacia 1890») and Spanish/English display;
  - the Mexican name model, with search folding and nickname (hipocorístico) variants;
  - the 110-year living rule, privacy sensitivity classes, the event vocabulary;
  - kinship labels in Spanish and English, compadrazgo;
  - a deterministic synthetic family generator.
- **GEDCOM engine** (`family_history.gedcom`):
  - GEDCOM 7.0 reading, strict or tolerant;
  - GEDCOM 5.5.1 import with an upgrade report;
  - deterministic 7.0 and 5.5.1 writers;
  - hardened GEDZIP;
  - mappings for Mexican names, padrinos and events, with four documented `_FH_` extension tags.
- **API service:**
  - Janua RS256 sign-in with scopes and an early-access allowlist;
  - row-level security forced on every table;
  - v1 create/read/update for spaces, people, relationships, events, places, sources, citations
    and assertions;
  - the waitlist endpoint;
  - a generated OpenAPI contract.
- **Web app:**
  - a Spanish-first landing, noindex by default, with structured data matching its FAQ;
  - a Janua sign-in app shell: families, people, person page, account settings.
- **Platform:** full CI gates and repo guards, Enclii and Kubernetes manifests, and a build
  workflow that only runs on manual dispatch.

**Does not exist yet**

- **Wiring between the library and the API.** Dates are stored as GEDCOM text with no computed
  bounds or display. Living status is not computed from events. There are no kinship,
  compadrazgo or search-variant endpoints.
- **GEDCOM import and export, and the full export.**
- **The family-tree view,** the relationship editor, media, stories and interviews.
- **Waitlist collection.** It stays off until the privacy notice is reviewed by counsel.
