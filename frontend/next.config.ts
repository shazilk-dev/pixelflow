import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
        pathname: "/**",
      },
      // Docker internal network (api service)
      {
        protocol: "http",
        hostname: "api",
        port: "8000",
        pathname: "/**",
      },
    ],
  },
};

export default nextConfig;
