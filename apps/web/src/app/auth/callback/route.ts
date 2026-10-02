import { handleCallback } from "@/lib/auth/handlers";

export const dynamic = "force-dynamic";

export function GET(request: Request): Promise<Response> {
  return handleCallback(request);
}
