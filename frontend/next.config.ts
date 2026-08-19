import type { NextConfig } from "next"

// No rewrites. Every /api/* path is served by a route handler in app/api/*,
// which forwards to BACKEND_URL (see lib/backend.ts).
//
// There used to be a rewrite here sending /api/:path* to http://localhost:8000.
// Array-form rewrites are matched BEFORE dynamic routes, so it silently
// intercepted /api/jobs and /api/jobs/[id]/* — the whole application tracker —
// and only static handlers like /api/resume ever ran. In dev the rewrite target
// is the real backend, so everything worked; deployed, it would have pointed at
// a port that does not exist inside the serverless container.
const nextConfig: NextConfig = {}

export default nextConfig
