import { routeApi } from "@/lib/api/route-support";
import { handleJobStatus } from "@/lib/jobs/handlers";

export const dynamic = "force-dynamic";

/** GET /api/app/jobs/<id>: the import or export job, for the page that polls it. */
export async function GET(_request: Request, { params }: { params: Promise<{ jobId: string }> }): Promise<Response> {
  return handleJobStatus((await params).jobId, routeApi);
}
