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
  },
};

export default withNextIntl(nextConfig);
