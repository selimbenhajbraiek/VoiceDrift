import path from "node:path";
import type { NextConfig } from "next";

// The Python backend (python -m backend.dashboard). 127.0.0.1 rather than localhost avoids a slow IPv6 attempt.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8700";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Pin the project root: a stray package-lock.json higher up (in the user folder) would otherwise be picked.
  turbopack: { root: path.resolve(__dirname) },
  // The browser only talks to this app; /api/* is forwarded to the backend, so its sign-in cookie is same-origin.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
  // Analyzing a Track-your-voice reading takes a few seconds (longer while the models load the first time)
  experimental: { proxyTimeout: 180_000 },
};

export default nextConfig;
