"use server";

import { loadAviso } from "@/lib/waitlist/aviso";
import { submitWaitlist } from "@/lib/waitlist/submit";
import type { WaitlistResult } from "@/lib/waitlist/types";

export async function joinWaitlistAction(_previous: WaitlistResult, form: FormData): Promise<WaitlistResult> {
  return submitWaitlist(form, {
    isAvisoPublished: async (version, locale) => (await loadAviso(version, locale)) !== null,
  });
}
