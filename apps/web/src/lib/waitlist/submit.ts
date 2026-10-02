/**
 * Waitlist submission, shared by the server action and the tests. Re-checks the gate on the
 * server (a hidden form is not a closed form), validates input, and posts
 * `{email, locale, consent: true, aviso_version}` to `${FH_API_INTERNAL_URL}/v1/waitlist`.
 */
import { z } from "zod";

import { isLocale, type Locale } from "@/i18n/locales";
import { createApiClient, type FetchLike } from "@/lib/api/client";
import { joinWaitlist } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import type { Env } from "@/lib/env";

import { waitlistState } from "./gate";
import type { WaitlistResult } from "./types";

export type { WaitlistError, WaitlistResult } from "./types";

const emailSchema = z.email().max(254);

export interface WaitlistDeps {
  env?: Env;
  fetchImpl?: FetchLike;
  isAvisoPublished: (version: string, locale: Locale) => Promise<boolean>;
}

export async function submitWaitlist(form: FormData, deps: WaitlistDeps): Promise<WaitlistResult> {
  const env = deps.env ?? process.env;
  const rawLocale = form.get("locale");
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "es";
  const email = String(form.get("email") ?? "").trim();

  const config = waitlistState(env);
  if (!config.open || !(await deps.isAvisoPublished(config.avisoVersion, locale))) {
    return { status: "error", error: "closed", email };
  }
  if (!emailSchema.safeParse(email).success) return { status: "error", error: "invalidEmail", email };
  if (form.get("consent") !== "on") return { status: "error", error: "consentRequired", email };

  const api = createApiClient({ fetchImpl: deps.fetchImpl }, env);
  try {
    await joinWaitlist(api, { email, locale, consent: true, aviso_version: config.avisoVersion });
    return { status: "success" };
  } catch (error) {
    if (isApiError(error) && (error.status === 429 || error.code === "rate_limited")) {
      return { status: "error", error: "rateLimited", email };
    }
    if (isApiError(error) && (error.status === 400 || error.status === 422)) {
      return { status: "error", error: "invalidEmail", email };
    }
    console.error("waitlist submission failed", isApiError(error) ? `${error.status} ${error.code}` : "unexpected error");
    return { status: "error", error: "unavailable", email };
  }
}
