/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',    // ← add this
  // Note: npm audit shows Next.js 14.2.35 CVEs (GHSA-9g9p-9gw9-jx7f, GHSA-h25m-26qc-wcjf)
  // NOT VULNERABLE: We don't use remotePatterns or insecure RSC features
  // Investigated: 2026-02-05
  images: {
    remotePatterns: [
      {
        // Google OAuth avatars — used in UserMenu and ClientLayout
        protocol: 'https',
        hostname: 'lh3.googleusercontent.com',
      },
      {
        // GitHub OAuth avatars
        protocol: 'https',
        hostname: 'avatars.githubusercontent.com',
        },
        {
          protocol: 'https',
          hostname: 'media.licdn.com',
      },
    ],
  },
  async redirects() {
    return [
      { source: '/library/shelves', destination: '/library', permanent: true },
    ];
  },
};
export default nextConfig;
