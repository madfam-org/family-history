import Script from "next/script";

import { plausibleConfig } from "@/lib/env";
import { requestNonce } from "@/lib/i18n/request-context";

/** Self-hosted Plausible on the landing only, and only when fully configured. */
export async function Analytics() {
  const config = plausibleConfig();
  if (!config) return null;
  const nonce = await requestNonce();
  return (
    <Script
      src={`${config.origin}/js/script.js`}
      data-domain={config.domain}
      strategy="afterInteractive"
      nonce={nonce}
    />
  );
}
