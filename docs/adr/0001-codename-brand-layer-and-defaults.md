# ADR 0001 — Codename, brand as a presentation layer, and starting defaults

> Last Updated: 2026-10-01

- **Status:** Accepted on owner direction, 2026-10-01 ("codename now, brand later"; "proceed with
  scaffolding, implementation and deployment").
- **Context:** The public brand is not ruled. Two candidates were dropped after collision checks
  with existing genealogy products.

## Decision

1. **`family-history` is the permanent internal identity.** It names the repository, the
   deployment project and namespace, database, images, bucket and identity clients. It never
   changes when the brand is chosen.
2. **The brand is a presentation layer.** The display name, copy, palette tokens, social images
   and public domains come from one brand configuration in the web app plus its message files.
   Rebranding is a configuration change plus a host cutover, not a rename.
3. **Working hosts:** `fh.madfam.io` (landing), `fh-app.madfam.io` (app), `fh-api.madfam.io`
   (API). All pages carry `noindex` until the brand is set, so no search equity builds on a
   temporary host.
4. **Licence:** public repository, AGPL-3.0-only.
5. **No private packages.** The repo must build anywhere, forks included. Until the ecosystem's
   public-safe packages are published to the public registry, sign-in uses a self-contained OIDC
   client (authorization code with PKCE S256) behind the ecosystem env contract `AUTH_JANUA_*`.
   This keeps the later swap mechanical.

## Consequences

- No identifier in code, manifests or the database depends on the brand.
- When the brand is ruled, the follow-up is a brand configuration PR and a host cutover. The
  internal identity stays.
