/** Turns API calls into explicit results so pages render every failure visibly. */
import { errorMessageKey, isApiError, type ErrorCode } from "./errors";

export type Loaded<T> = { ok: true; data: T } | { ok: false; code: ErrorCode; status: number };

export async function load<T>(call: () => Promise<T>): Promise<Loaded<T>> {
  try {
    return { ok: true, data: await call() };
  } catch (error) {
    if (isApiError(error)) return { ok: false, code: errorMessageKey(error.code), status: error.status };
    throw error;
  }
}
