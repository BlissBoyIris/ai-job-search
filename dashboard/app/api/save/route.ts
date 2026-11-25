import { NextResponse } from "next/server";
import { setSaved } from "../../../lib/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Save jobs for later ({ keys, saved: true }) or move them back to Open ({ keys, saved: false }). */
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const keys: string[] = Array.isArray(body.keys) ? body.keys.map(String) : [];
  if (keys.length === 0) return NextResponse.json({ error: "Nothing selected" }, { status: 400 });
  setSaved(keys, body.saved !== false);
  return NextResponse.json({ ok: true, count: keys.length });
}
