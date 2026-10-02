import { routeApi } from "@/lib/api/route-support";
import { handleJobDownload } from "@/lib/jobs/handlers";

export const dynamic = "force-dynamic";

/** GET /api/app/jobs/<id>/download: streams the finished file (410 after 24 hours). */
export async function GET(request: Request, { params }: { params: Promise<{ jobId: string }> }): Promise<Response> {
  return handleJobDownload(request, (await params).jobId, routeApi);
}
