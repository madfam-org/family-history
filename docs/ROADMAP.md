# Roadmap

> Last Updated: 2026-10-01
>
> Boundary checkpoint (2026-10-01): public roadmap. It lists product milestones, launch gates and
> follow-ups only. Operator procedures, owner gates and internal decisions are tracked in MADFAM's
> private internal-devops repository under the repo-boundary contract.

[HONEST_STATUS.md](./HONEST_STATUS.md) says what works today. This file says what comes next and
in what order. Milestones are defined by scope and exit gates, not by dates.

## Milestones

| Milestone | Scope | Exit gate | State |
|---|---|---|---|
| **M0 Cimientos** | Repository, licence, agent docs, contracts, CI gates and guards, deployment manifests, the landing and the app shell | Working hosts live (noindex), CI green, sign-in works for allowlisted accounts | Code on `main`; **deployment pending** (platform onboarding, sign-in client, secrets, DNS) |
| **M1 Árbol** | Wiring the genealogy library and GEDCOM engine into the API; tree view; relationship and godparent editors; kinship lookup; GEDCOM import; the free full export with a byte-identical round trip; a Postgres-backed job queue and worker | Real use on synthetic families only; export round trip byte-identical in CI | Engines and API core on `main`; **integration in progress** |
| **M2 Historias** | Written stories (relatos); guided interviews in Spanish (`usted` for elders); in-browser recording; invitations by email and `wa.me` links; timeline; private ofrenda view; consent records; privacy requests and «Quítame de este árbol» | Privacy notice reviewed by counsel; privacy-request deadlines tracked | Not started |
| **M3 Asistencia** | Story drafts and summaries as AI *suggestions* (MADFAM inference gateway, `restricted` sensitivity); reading actas and parish books (document-reading service, new document types contributed upstream); photo restoration as labelled derivatives; read-only agent tools generated from the OpenAPI | The gateway can serve `restricted` data; a speech-to-text owner is decided | Not started |
| **M4 Comunidad** | Paid tiers (`free`, `family`, `society`) once priced; opt-in memorial pages for the deceased with structured data; QR plaques; brand ruling and the move from working hosts to the product's own domain | Launch gates below | Not started |

## Launch gates

No real family's data goes in before all of these hold:

1. **Backups proven.** A database restore drill has passed, with a stated recovery point and time.
2. **Media durability.** Media originals have a second copy.
3. **Privacy notice.** The aviso de privacidad (integral and simplified) is reviewed by counsel.
   The waitlist stays off until then.
4. **Security review.** A full review of the API, web app and deployment.
5. **Alerting.** Alerts reach a person and every alert has a runbook entry.
6. **Privacy requests.** Requests are handled end to end within 20 business days, including people
   who never signed up.

## Product decisions still open

- **Speech-to-text for interviews:** which MADFAM service owns transcription.
- **Minors:** accounts stay adults-only; whether to add age and parental-consent support in the
  identity provider.
- **Tiers and prices:** shape (`free`, `family`, `society`) and prices, set through MADFAM's
  pricing process. Export stays free at every tier.
- **Brand:** the public name and domain. `family-history` remains the internal codename (ADR 0001).

## Dependency holds

Lift each hold deliberately, in its own PR, with the migration it needs.

| Hold | Why |
|---|---|
| `sqlalchemy>=2.0,<2.1` (Dependabot ignores `>=2.1`) | SQLAlchemy 2.1 changes `Select`/`Row` typing and breaks strict mypy. Lift together with the typing migration |
| `next` pinned exactly to `16.3.8` | Security floor for GHSA-vcvr-r3jv-pc5j. Bump deliberately with `eslint-config-next` |
| Majors of `typescript` and `zod` (Dependabot ignores semver-major) | These majors move across MADFAM's repositories together, as one planned migration. Minor and patch updates still arrive |
| CI runners pinned to `ubuntu-24.04` | `ubuntu-latest` moves to a new image on 2026-10-19. Move after testing on the new image |
| Org quality gates run as scripts | The shared workflow still pins its actions by tag, which this repo's SHA-pinning rule refuses. Call it directly once it pins by SHA |

## Known follow-ups

- **Rate limiting.** The waitlist rate limiter is in-process, which suits a single replica only. It
  needs a shared store and a stable salt setting before scaling out.
- **Error reporting.** `FH_SENTRY_DSN` is parsed but inert until the SDK is added.
- **Membership management.** Inviting and removing members waits for the identity provider's
  organization binding.
- **Token verification inside the cluster.** Pin the identity provider's signing-key thumbprints.
- **Deploy workflow.** Builds run only on manual dispatch until onboarding is complete; then switch
  to push-on-main.
