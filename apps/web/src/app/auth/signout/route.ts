import { handleSignOut } from "@/lib/auth/handlers";

export const dynamic = "force-dynamic";

export function POST(request: Request): Promise<Response> {
  return handleSignOut(request);
}
