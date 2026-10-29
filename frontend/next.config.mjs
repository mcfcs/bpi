// Where the FastAPI backend runs, as seen from the Next.js server. The browser never calls it
// directly: /api/* is proxied (see rewrites), so the app works from any host that can reach Next,
// including other devices on a Tailscale tailnet, with only one port exposed.
const backendUrl = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

// Extra hostnames allowed to load dev-only assets (`next dev` only). Comma-separated, no scheme or
// port, e.g. "100.102.10.69,my-pc.tail1234.ts.net".
const devOrigins = (process.env.DEV_ORIGINS ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Pin the project root so a stray lockfile higher up the tree is not mistaken for it.
  turbopack: { root: import.meta.dirname },
  allowedDevOrigins: ["*.ts.net", "**.ts.net", ...devOrigins],
  // A Claude-written brief (a draft plus at most one regeneration) can take far longer than the
  // 30 s default proxy timeout.
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
