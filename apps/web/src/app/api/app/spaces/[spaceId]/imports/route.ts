import { routeApi } from "@/lib/api/route-support";
import { handleImportUpload } from "@/lib/jobs/handlers";

export const dynamic = "force-dynamic";

/** POST /api/app/spaces/<id>/imports: a .ged or .gdz upload, streamed to the API. */
export async function POST(request: Request, { params }: { params: Promise<{ spaceId: string }> }): Promise<Response> {
  return handleImportUpload(request, (await params).spaceId, routeApi);
}
