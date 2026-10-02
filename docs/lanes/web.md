# Lane notes: web (`apps/web`)

> Last Updated: 2026-10-01

One Next.js 16.3.8 standalone server (`@family-history/web`, AGPL-3.0-only) serves both the
public landing and the signed-in app, routed by host. Spanish (es-MX) first, English second.

## What was built

- **Workspace.** Root `package.json` (`packageManager: pnpm@9.15.0`), `pnpm-workspace.yaml`
  (`apps/*`, `packages/*`), project-level `.npmrc`. Pinned: `next` 16.3.8 and
  `eslint-config-next` 16.3.8 (GHSA-vcvr-r3jv-pc5j), React 19.2.8, TypeScript 5.9.3,
  Tailwind CSS 4.3, next-intl 4.14, jose 6, zod 4, Vitest 4 (Vitest 5 needs Node ≥ 22.12).
- **Host routing** (`src/proxy.ts` → `src/lib/routing/host-routing.ts`). Public paths are
  rewritten to two internal trees, `/<locale>/site/...` (landing) and `/<locale>/workspace/...`
  (app). The internal segments return 404 from outside. Unknown hosts get the landing.
- **Brand as configuration** (`src/lib/brand.ts`, ADR 0001). The interim names «Historia
  Familiar» and "Family History", the tagline, the endorsement line and the colour tokens all live
  here. A test fails if a message file hard-codes the display name.
- **Security headers** on every response: a nonce-based CSP with `'strict-dynamic'` and no
  `unsafe-inline` or `unsafe-eval` in production, plus HSTS (HTTPS only), nosniff,
  `frame-ancestors 'none'`, a Permissions-Policy and COOP. `poweredByHeader: false`.
- **Indexing.** Unless `FH_INDEXABLE` is exactly `true`, every response carries
  `X-Robots-Tag: noindex, nofollow`, pages carry meta robots noindex, and `robots.txt`
  disallows everything. When it is `true`, `robots.txt` follows ruling R40 on the landing.
  The app host is always noindex.
- **OIDC client** (`src/lib/auth/*`, no private packages):
  - Discovery: the document's issuer must match the configured one; `registration_endpoint` is
    never read; an issuer without S256 or RS256 is rejected; endpoints must be HTTPS.
  - Sign-in uses PKCE S256, `state` and `nonce`. The confidential token exchange runs
    server-side (`client_secret_basic` when advertised, else `client_secret_post`).
  - ID tokens: RS256 only, verified through JWKS; issuer, audience = client id, `azp` and nonce
    are all checked.
  - Session: an encrypted JWE (`dir` + A256GCM) in an httpOnly, `__Host-`, Secure, SameSite=Lax
    cookie, chunked under 4 KB per cookie. Keys are derived from `FH_SESSION_SECRET` with HKDF,
    one key per purpose; the Janua client secret is never used for sessions (R42).
    Lifetimes: 8 hours idle and 7 days absolute.
  - Refresh-token rotation runs in the proxy. It is single-flight per refresh token and
    remembers rotations for 30 seconds, so parallel or late requests never replay a rotated
    token.
  - Scopes requested: `openid profile email offline_access fh:read fh:write`.
- **API client** (`src/lib/api/*`): typed with zod from the v1 contract, aligned with the API
  lane's actual schemas (`PersonCreate` with `apellido_paterno` and `apellido_materno`). Every
  failure becomes a visible `ApiError` code, and the UI maps codes to es and en copy.
  `403 early_access_required` shows «Tu cuenta aún no tiene acceso anticipado».
- **Waitlist** (`src/lib/waitlist/*`). The form renders only when **all** of these hold:
  - `FH_WAITLIST_ENABLED=true`;
  - `FH_AVISO_VERSION` is set;
  - the counsel-reviewed notice `content/aviso/<version>.<locale>.txt` exists.

  The server action re-checks the gate, so a forged post collects nothing. When it is closed,
  the landing says «Muy pronto: acceso anticipado por invitación». No legal text was written;
  `content/aviso/README.md` says what goes there.
- **Dockerfile** (`apps/web/Dockerfile`, context: the repository root). Both stages use
  `node:22-alpine@sha256:0a7108bf…e402` (the current `22-alpine` index digest on 2026-10-01).
  pnpm runs through corepack with `--filter @family-history/web...`.
  - The runtime stage removes npm, npx, corepack and yarn.
  - The image runs as `USER 1001` from `WORKDIR /app` and starts `node apps/web/server.js`.
  - `/app/apps/web/.next/cache` is a symlink to `/app/.next/cache`, the writable emptyDir.
  - The build fails unless `server.js` exists.
  - There are no build-time secrets and no `NEXT_PUBLIC_*` values.

  `apps/web/Dockerfile.dockerignore` is an allowlist.

## Pages

| Host | Public path | What it is |
|---|---|---|
| landing | `/` | 307 to `/es` |
| landing | `/es`, `/en` | Landing: hero, «Cómo funciona», «Hecho para familias mexicanas», privacy promises, waitlist or «Muy pronto», visible FAQ. JSON-LD `Organization` + `SoftwareApplication` + `FAQPage` in the server HTML. No price anywhere |
| landing | `/es/aviso-de-privacidad`, `/en/...` | The reviewed notice, or «Aviso de privacidad en revisión» |
| app | `/es`, `/en` | «Mis familias»: list spaces, create a space |
| app | `/es/familias/<id>` | A family space: people with search and paging, «Agregar persona», and a labelled «Próximamente» tree section |
| app | `/es/personas/<id>` | A person: names, events, relationships and cited sources, with empty states |
| app | `/es/ajustes` | Account, «Cambiar de cuenta» (`prompt=select_account`), «Entrar como otra persona» (`prompt=login`), «Cerrar sesión» |
| app | `/es/entrar` | Sign-in page. Signed-out visitors land here, never straight at the issuer. It also shows sign-in errors |
| app | `/auth/start`, `/auth/callback`, `/auth/signout` | OIDC routes. Sign-out is a POST with an Origin check, then RP-initiated logout |
| any | `/api/health` | `200 {"status":"ok"}`, no dependency checks |
| any | `/robots.txt`, `/sitemap.xml`, `/llms.txt`, `/og.png`, `/icon.svg`, `/.well-known/security.txt` | Site files |

Mobile-first at 360 px:
- WCAG AA contrast, with the ratios recorded in `globals.css` and `brand.ts`;
- a skip link;
- a visible `:focus-visible` ring;
- 44 px touch targets;
- `prefers-reduced-motion` honoured;
- light and dark themes through `prefers-color-scheme`.

## Environment

| Variable | Use |
|---|---|
| `FH_ENV` | `local` turns off Secure cookies and `upgrade-insecure-requests`, and uses `http`. Unset means production |
| `FH_PUBLIC_LANDING_HOST`, `FH_PUBLIC_APP_HOST` | Host routing, public origins, redirect URIs |
| `FH_INDEXABLE` | Only the exact string `true` enables indexing |
| `AUTH_JANUA_ISSUER`, `AUTH_JANUA_CLIENT_ID`, `AUTH_JANUA_CLIENT_SECRET` | OIDC. If any is missing, `/auth/*` fail closed with «El inicio de sesión no está configurado» |
| `FH_SESSION_SECRET` | 32 bytes or more; shorter counts as not configured |
| `FH_API_INTERNAL_URL` | Server-side API base. Unset shows `api_not_configured` in the app |
| `FH_PLAUSIBLE_DOMAIN` + `FH_PLAUSIBLE_ORIGIN` | Optional analytics, landing only, both required, HTTPS origin |
| `FH_WAITLIST_ENABLED`, `FH_AVISO_VERSION` | Waitlist gate (see above) |

The landing and `/api/health` work with every auth and API variable unset. Checked by booting
the standalone build that way.

## Run locally

```bash
corepack enable && pnpm install
cd apps/web
FH_ENV=local FH_PUBLIC_LANDING_HOST=localhost:3000 FH_PUBLIC_APP_HOST=app.localhost:3000 \
FH_API_INTERNAL_URL=http://localhost:8000 FH_SESSION_SECRET="$(openssl rand -hex 32)" \
AUTH_JANUA_ISSUER=… AUTH_JANUA_CLIENT_ID=… AUTH_JANUA_CLIENT_SECRET=… pnpm dev
# landing: http://localhost:3000/es    app: http://app.localhost:3000/es
```

`next dev` writes `apps/web/AGENTS.md` and `apps/web/CLAUDE.md`, which are Next 16's agent hints.
They are not committed; see the contract requests.

## Tests and gates

`pnpm --filter @family-history/web run lint|typecheck|test|build`. `typecheck` runs
`next typegen && tsc --noEmit`.

There are 106 Vitest tests in 13 files:
- host routing, plus the proxy's noindex, CSP and second pass;
- PKCE (the RFC 7636 vector), state and nonce;
- session round trip, tamper rejection, key separation, lifetimes and cookie chunking;
- discovery hardening, ID-token checks (nonce, aud, azp, iss, HS256 refused) and rotation;
- the full start, callback and sign-out flow against a local RS256 issuer;
- FAQ ↔ JSON-LD parity, rendered with `react-dom/server`;
- es/en key, placeholder and tag parity, no brand names and no prices in the messages;
- API error-code mapping and contract drift;
- waitlist gating and submission;
- robots (R40) and llms.txt;
- CSP;
- form mapping;
- the language switch.

Also verified by hand:
- the standalone build in a browser at 360 px, light and dark, with no CSP violations;
- the whole app flow against a local synthetic mock of Janua and the API: sign-in, create a
  space, add a person, the birth-date notice, refresh rotation, «Cambiar de cuenta», sign-out,
  and the waitlist submit;
- the server booting from a non-writable copy of the image layout, with only the cache
  directory writable and no Janua configured: `/api/health` 200.

`pnpm audit --audit-level critical`: no known vulnerabilities. Production licences are MIT,
Apache-2.0, ISC, BSD, 0BSD and CC-BY-4.0 (caniuse-lite), plus one LGPL-3.0-or-later package
(`@img/sharp-libvips-*`, an optional dependency of `next`). That package is in the
licence gate's *review* class, which passes.

**Not verified locally:** `docker build`. The local Docker daemon hung on every registry and
`run` operation; other sessions' Docker commands were stuck as well. The image is built and
smoke-tested by the platform lane's `guards` job.

## Contract requests

1. **Environment table** (`docs/ARCHITECTURE.md`): add `FH_WAITLIST_ENABLED`,
   `FH_AVISO_VERSION` and `FH_PLAUSIBLE_ORIGIN` for web. `FH_PLAUSIBLE_DOMAIN` alone cannot
   locate a self-hosted Plausible.
2. **Free-text dates.** `EventCreate.date_value` accepts only GEDCOM grammar (uppercase tokens),
   so «hacia 1890» is rejected with 422. The web creates the person first, then posts a `birth`
   event with the text exactly as written. On rejection it shows «La persona se guardó, pero la
   fecha de nacimiento no…» rather than dropping the date silently.
   - Request: accept the original text (for example `date_original`) and derive `date_value`
     server-side, as the data model says («the original text is kept»).
3. **v1 table.** Add `POST /v1/spaces/{space_id}/events` and the full `Person`, `NameForm`,
   `Event`, `Relationship` and `Citation` shapes. The web follows the API lane's schemas.
4. **Janua.** Confirm that `scope=… fh:read fh:write` yields an access token with
   `aud=family-history-api` and those scopes. Confirm that Janua honours `prompt=select_account`
   and `prompt=login` (R44). The post-logout redirect is exactly `https://fh-app.madfam.io/`, as
   in `janua.client.yaml`.
5. **`.gitignore`:** decide whether to commit or ignore Next 16's generated `apps/web/AGENTS.md`
   and `apps/web/CLAUDE.md`.
6. **`.dockerignore`:** BuildKit uses `apps/web/Dockerfile.dockerignore`, an allowlist, instead
   of the root `.dockerignore` for this image.
7. **HONEST_STATUS:** the web landing and app now exist and are not deployed. The waitlist is
   off until counsel's notice is published. The tree view, media, stories and exports do not
   exist.
