import { NextRequest, NextResponse } from "next/server"
import { BACKEND } from "@/lib/backend"

// A full fan-out search takes 20–30s, so this needs a raised duration.
// 60 is the ceiling on Vercel's Hobby plan; asking for more fails the deploy.
// Local dev ignores this entirely.
export const maxDuration = 60

export async function POST(req: NextRequest) {
  try {
    const body = await req.formData()
    const res  = await fetch(`${BACKEND}/api/search`, {
      method:  "POST",
      body,
      // Must stay under maxDuration, or the platform kills the function first
      // and the client gets an opaque 504 instead of this handler's 502 + message.
      signal: AbortSignal.timeout(55_000),
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Search failed"
    return NextResponse.json({ detail: msg }, { status: 502 })
  }
}
