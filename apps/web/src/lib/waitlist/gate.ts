/**
 * The waitlist collects personal data, so it renders only when all of these hold:
 * - FH_WAITLIST_ENABLED is exactly `true`;
 * - FH_AVISO_VERSION is set (the counsel-reviewed privacy notice version);
 * - that notice is actually published for the page's locale.
 * Otherwise the landing says «Muy pronto: acceso anticipado por invitación».
 */
import { waitlistConfig, type Env } from "@/lib/env";

export type WaitlistState = { open: true; avisoVersion: string } | { open: false };

export function waitlistState(env: Env = process.env, avisoPublished = true): WaitlistState {
  const config = waitlistConfig(env);
  if (!config.enabled || !config.avisoVersion || !avisoPublished) return { open: false };
  return { open: true, avisoVersion: config.avisoVersion };
}
