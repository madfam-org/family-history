import { ImageResponse } from "next/og";

import { brand, brandName, brandTagline } from "@/lib/brand";

/** Static social image, rendered once at build time. */
export const dynamic = "force-static";

export function GET(): ImageResponse {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px",
          background: brand.colors.amate,
          color: brand.colors.ink,
        }}
      >
        <div style={{ display: "flex", width: "160px", height: "12px", background: brand.colors.grana }} />
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 88, fontWeight: 700, color: brand.colors.grana }}>{brandName("es")}</div>
          <div style={{ fontSize: 40, marginTop: 24, color: brand.colors.bark, maxWidth: "900px" }}>
            {brandTagline("es")}
          </div>
        </div>
        <div style={{ display: "flex", fontSize: 28, color: brand.colors.ink }}>{brand.endorsement.es}</div>
      </div>
    ),
    { width: 1200, height: 630 },
  );
}
