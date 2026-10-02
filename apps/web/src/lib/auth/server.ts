/**
 * Session access for Server Components and Server Actions. Pages read the session (already
 * rotated by the proxy when needed); they never write cookies.
 */
import "server-only";

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import { createApiClient, type ApiClient } from "@/lib/api/client";
import { sessionSecret } from "@/lib/env";
import { PATHNAME_HEADER } from "@/lib/routing/request-headers";

import { cookieName, readChunked, SESSION_COOKIE_BASE } from "./cookies";
import { accessTokenIsUsable, decryptSession, type SessionData } from "./session";
import { localeOfPath, safeReturnTo } from "./transaction";

export async function getSession(): Promise<SessionData | null> {
  const secret = sessionSecret();
  if (!secret) return null;
  const jar = await cookies();
  const raw = readChunked(
    cookieName(SESSION_COOKIE_BASE),
    jar.getAll().map(({ name, value }) => ({ name, value })),
  );
  const session = await decryptSession(raw, secret);
  if (!session || !accessTokenIsUsable(session)) return null;
  return session;
}

/** The public path of the current request, set by the proxy; used as the post-sign-in target. */
export async function currentPublicPath(): Promise<string> {
  return safeReturnTo((await headers()).get(PATHNAME_HEADER));
}

export function signInHref(returnTo: string, prompt?: "select_account" | "login"): string {
  const params = new URLSearchParams({ return_to: safeReturnTo(returnTo) });
  if (prompt) params.set("prompt", prompt);
  return `/auth/start?${params.toString()}`;
}

/** The app's sign-in page for a locale, remembering where to return. */
export function signInPageHref(returnTo: string): string {
  const target = safeReturnTo(returnTo);
  return `/${localeOfPath(target)}/entrar?${new URLSearchParams({ return_to: target }).toString()}`;
}

/**
 * Sends a visitor without a usable session to the sign-in page (not straight to the issuer, so
 * signing out is never undone by an issuer-side session).
 */
export async function requireSession(): Promise<SessionData> {
  const session = await getSession();
  if (!session) redirect(signInPageHref(await currentPublicPath()));
  return session;
}

export async function requireApi(): Promise<{ session: SessionData; api: ApiClient }> {
  const session = await requireSession();
  return { session, api: createApiClient({ accessToken: session.accessToken }) };
}
