# Ecosystem roles

> Last Updated: 2026-10-01
>
> Boundary checkpoint (2026-10-01): roles only. MADFAM's private internal-devops repository owns
> topology, operator procedures and secret handling; see the repo-boundary contract there.

`family-history` is one product in the MADFAM ecosystem. It owns these capabilities:
- the family graph;
- GEDCOM import and export;
- the living-person privacy engine;
- the oral-history and media archive;
- the historical place gazetteer.

It **consumes** everything else and never re-implements it:

| Capability | Owner | How family-history uses it |
|---|---|---|
| Sign-in, sessions, MFA, passkeys | Janua (`auth.madfam.io`) | OIDC authorization code with PKCE; RS256 tokens verified through JWKS |
| Families as tenants, entitlements | Janua | A family space binds to a Janua organization; paid plans arrive as an entitlement claim |
| Billing, invoices, tax | Dhanam | Upgrade links only. No payment keys here |
| Transactional email | Janua | Invitations, export-ready notices, privacy-request receipts |
| LLM text and vision | Selva | Story drafts and summaries as suggestions, at `restricted` or `confidential` sensitivity |
| Reading old documents | tlacuilo | Extraction of actas and parish records |
| Photo restoration | ceq | Restored copies are labelled and never used as evidence |
| Waitlist and marketing consent | PhyndCRM | Double opt-in |
| QR codes, short links | marca | Memorial plaques |
| Third-party messaging | Angelia Courier | Until it is enabled, invitations use `wa.me` links |
| Deploy, DNS, secrets, Postgres, object storage | Enclii | Everything runtime |
| Analytics | Self-hosted Plausible | Cookieless |
