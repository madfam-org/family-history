/**
 * API error codes and their mapping to message keys under `errors.*`. The API sends English
 * messages; families only ever see the Spanish (or English) copy chosen here.
 */
export const KNOWN_ERROR_CODES = [
  "early_access_required",
  "unauthorized",
  "forbidden",
  "not_found",
  "validation_error",
  "conflict",
  "rate_limited",
  "server_error",
  "api_unreachable",
  "api_not_configured",
  "invalid_response",
  "unknown",
] as const;

export type ErrorCode = (typeof KNOWN_ERROR_CODES)[number];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Code to use when the response carries no valid error envelope. */
export function codeForStatus(status: number): ErrorCode {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 400 || status === 422) return "validation_error";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "server_error";
  return "unknown";
}

const ALIASES: Readonly<Record<string, ErrorCode>> = {
  invalid_token: "unauthorized",
  token_expired: "unauthorized",
  authentication_required: "unauthorized",
  permission_denied: "forbidden",
  space_not_found: "not_found",
  person_not_found: "not_found",
  invalid_request: "validation_error",
  insufficient_scope: "forbidden",
  too_many_requests: "rate_limited",
  internal_error: "server_error",
};

/** Maps any API error code to a message key under `errors.*`. Unknown codes never leak through. */
export function errorMessageKey(code: string): ErrorCode {
  if ((KNOWN_ERROR_CODES as readonly string[]).includes(code)) return code as ErrorCode;
  if (code.endsWith("_not_found")) return "not_found";
  return ALIASES[code] ?? "unknown";
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
