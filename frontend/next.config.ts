import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Host names that may open the dev server through a tunnel, comma separated (set by scripts/start-real.ps1),
  // e.g. abc123-3000.inc1.devtunnels.ms. Empty means localhost only.
  allowedDevOrigins: (process.env.ALLOWED_DEV_ORIGINS ?? "").split(",").map((h) => h.trim()).filter(Boolean),
  // AI drafts (LLM + Meta lookups + image) can take over a minute; the /api proxy's default is 30 s.
  experimental: { proxyTimeout: 120_000 },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
      },
    ],
  },
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backendUrl}/:path*` },
      { source: "/api/:path*", destination: `${backendUrl}/:path*` },
    ];
  },
};

export default nextConfig;
