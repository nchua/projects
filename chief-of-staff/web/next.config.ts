import type { NextConfig } from "next";

const apiUrl =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const isTauriBuild = !!process.env.TAURI_ENV_PLATFORM;

const nextConfig: NextConfig = {
  // Tauri needs static export; browser dev uses rewrites
  ...(isTauriBuild
    ? {
        output: "export",
        images: { unoptimized: true },
      }
    : {
        async rewrites() {
          return [
            {
              source: "/api/v1/:path*",
              destination: `${apiUrl}/api/v1/:path*`,
            },
          ];
        },
      }),
};

export default nextConfig;
