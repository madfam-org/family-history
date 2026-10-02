import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // The aviso de privacidad is read from disk at request time; ship its files in the standalone build.
  outputFileTracingIncludes: {
    "/*": ["./content/**/*"],
  },
  experimental: {
    serverActions: {
      bodySizeLimit: "64kb",
    },
    // GEDCOM imports stream through /api/app/spaces/<id>/imports: 25 MiB of file plus the
    // multipart envelope. The proxy buffers request bodies up to this size (default 10 MB, and
    // larger bodies would be cut short); the route handler itself rejects anything bigger.
    proxyClientMaxBodySize: "26mb",
  },
};

export default withNextIntl(nextConfig);
