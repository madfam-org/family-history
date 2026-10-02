/** Waitlist result types, shared by the server action and the client form (no server imports). */
export type WaitlistError = "invalidEmail" | "consentRequired" | "rateLimited" | "unavailable" | "closed";

export type WaitlistResult =
  | { status: "idle" }
  | { status: "success" }
  | { status: "error"; error: WaitlistError; email: string };

export const initialWaitlistResult: WaitlistResult = { status: "idle" };
