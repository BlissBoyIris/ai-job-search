import fs from "node:fs";
import path from "node:path";
import { safePdf } from "../../../lib/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const rel = new URL(req.url).searchParams.get("path") ?? "";
  const abs = safePdf(rel);
  if (!abs) return new Response("Not found", { status: 404 });
  return new Response(fs.readFileSync(abs), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `inline; filename="${path.basename(abs)}"`,
      "Cache-Control": "no-store",
    },
  });
}
