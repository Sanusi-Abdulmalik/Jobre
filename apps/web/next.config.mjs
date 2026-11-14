/** @type {import('next').NextConfig} */
const apiTarget = process.env.INTERNAL_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  output: process.env.DOCKER_STANDALONE === "1" ? "standalone" : undefined,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiTarget}/api/v1/:path*`,
      },
      {
        source: "/metrics",
        destination: `${apiTarget}/metrics`,
      },
      {
        source: "/docs",
        destination: `${apiTarget}/docs`,
      },
      {
        source: "/openapi.json",
        destination: `${apiTarget}/openapi.json`,
      },
    ];
  },
};

export default nextConfig;
