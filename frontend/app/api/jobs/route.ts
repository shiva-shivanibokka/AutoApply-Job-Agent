import { NextRequest, NextResponse } from "next/server"
import { BACKEND } from "@/lib/backend"

// GET /api/jobs — backs the "My Pipeline" view (status=tracked).
//
// This handler used to be missing: requests fell through to a rewrite in
// next.config.ts that pointed at http://localhost:8000, which happens to be the
// real backend in dev, so the gap was invisible locally and would only surface
// once deployed. The rewrite is gone; every /api/* path now needs a handler.
export async function GET(req: NextRequest) {
  try {
    const qs = req.nextUrl.searchParams.toString()
    const res = await fetch(`${BACKEND}/api/jobs${qs ? `?${qs}` : ""}`, {
      signal: AbortSignal.timeout(15_000),
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Failed to load jobs"
    return NextResponse.json({ detail: msg }, { status: 502 })
  }
}
