import { NextResponse } from "next/server";
import { buildJobs } from "../../../lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(buildJobs());
}
