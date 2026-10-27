/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Pin the project root so a stray lockfile higher up the tree is not mistaken for it.
  turbopack: { root: import.meta.dirname },
};

export default nextConfig;
