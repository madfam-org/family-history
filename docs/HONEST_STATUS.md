# Honest status

> Last Updated: 2026-10-02

This is the only list of what works. When behaviour changes, update this file in the same PR.

## 2026-10-02: build waves 1 and 2 (on `main`)

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
  - row-level security forced on every table, the job queue included;
  - v1 create/read/update for spaces, people, relationships, events, places, sources, citations
    and assertions;
  - event dates from GEDCOM 7 or from Spanish text, with bounds and Spanish/English display;
  - living status computed from cited death evidence and the 110-year rule, in Mexico City time;
  - ranked people search that folds spelling and knows nicknames («Chucho» finds Jesús);
  - kinship, compadrazgo, and godparents, witnesses and officiants on events;
  - import (GEDCOM 7, GEDCOM 5.5.1, GEDZIP, native JSON; 25 MiB) and export (the same four
    formats) as background jobs. The export is free at every tier;
  - the native format `family-history-tree/v1`: export, import into an empty space, then export
    again gives a byte-identical file. CI proves it for the native format and for GEDCOM 7;
  - the worker (`python -m family_history.worker`) on a Postgres job queue, with lease, retry
    and expiry;
  - the waitlist endpoint, closed (`404 waitlist_closed`) until it is switched on with a reviewed
    privacy notice;
  - a generated OpenAPI contract and the native format's JSON Schema, both drift-checked.
- **Web app:**
  - a Spanish-first landing, noindex by default, with structured data matching its FAQ;
  - a Janua sign-in app shell: families, people, person page, account settings;
  - a person editor with the Mexican name model and free-text dates with Spanish hints;
  - relationship and godparent editors, and a compadrazgo panel;
  - a family-tree view (ancestors and descendants) with an accessible list version;
  - «¿Cómo estamos emparentados?», the kinship lookup;
  - GEDCOM and native import, and «Llévate todo» export, with job progress and Spanish reports;
  - tests that check every response the web parses against the API's OpenAPI.
- **Checked by hand once, not in CI:** the web against a local API and worker (import, export,
  re-import of the export), with the API's local synthetic principal instead of a Janua token.
- **Platform:** full CI gates and repo guards, Enclii and Kubernetes manifests for the web, the
  API and the worker, and a build workflow that only runs on manual dispatch.

**Does not exist yet**

- **Deployment.** No host, database or sign-in client exists yet.
- **Media.** Photos and documents, and the media inside GEDZIP files (imports skip them with a
  warning).
- **Stories and memory** (milestone M2): written stories, interviews, timeline, invitations,
  consent records and privacy requests.
- **Editing gaps in the web app:** places, privacy and visibility, and citing sources.
- **A tree endpoint.** The tree view loads relatives one request at a time, up to 80 people.
- **Waitlist collection.** It stays off, in the API and in the web, until the privacy notice is
  reviewed by counsel.

**Open question that changes behaviour**

- **What proves a death.** Today any current cited assertion about a death, burial or cremation
  that is not retracted or disputed ends the living presumption. The stricter option counts
  accepted assertions only. It is decided before real data goes in
  ([ROADMAP.md](./ROADMAP.md#product-decisions-still-open)).
