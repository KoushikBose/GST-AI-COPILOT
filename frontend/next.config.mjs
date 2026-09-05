/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  eslint: {
    dirs: ["app", "components", "hooks", "lib", "types"],
  },
};

export default nextConfig;
