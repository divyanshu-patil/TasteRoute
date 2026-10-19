import process from "node:process";

// NEXT_PUBLIC_API_URL is baked into the bundle at build time. On Vercel it must name the deployed API, not this site:
// a build pointing at itself shipped a demo whose every API call was a 404 (docs/16-runbook.md).
if (process.env.VERCEL) {
  const api = process.env.NEXT_PUBLIC_API_URL ?? "";
  const host = URL.canParse(api) ? new URL(api).host : "";
  const self = [process.env.VERCEL_URL, process.env.VERCEL_BRANCH_URL, process.env.VERCEL_PROJECT_PRODUCTION_URL];
  if (!host || host.startsWith("localhost") || self.includes(host)) {
    throw new Error(`NEXT_PUBLIC_API_URL must be the deployed API's URL (got "${api}"). Set it in Vercel and redeploy.`);
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {};

export default nextConfig;
