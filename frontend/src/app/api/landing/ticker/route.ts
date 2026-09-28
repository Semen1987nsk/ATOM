import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
  try {
    const r = await fetch(`${BACKEND}/api/landing/ticker`, { next: { revalidate: 60 } });
    if (!r.ok) {
      return NextResponse.json({ stale: true, tickers: [], fallback: true }, { status: 200 });
    }
    const body = await r.json();
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ stale: true, tickers: [], fallback: true }, { status: 200 });
  }
}
