import { routeApi } from "@/lib/api/route-support";
import { handleImportUpload } from "@/lib/jobs/handlers";

export const dynamic = "force-dynamic";

/** POST /api/app/spaces/<id>/imports: a .ged, .gdz or .json upload, streamed to the API (which checks the type). */
export async function POST(request: Request, { params }: { params: Promise<{ spaceId: string }> }): Promise<Response> {
  return handleImportUpload(request, (await params).spaceId, routeApi);
}
