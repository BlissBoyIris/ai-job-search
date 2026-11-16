// Only this machine's own browser tab may talk to the API. Without this, any web
// page the user visits could POST to 127.0.0.1:3300 and start paid Claude runs,
// or read the job list through DNS rebinding.
import { NextResponse, type NextRequest } from "next/server";

const HOSTS = new Set(["127.0.0.1:3300", "localhost:3300"]);

export function middleware(req: NextRequest) {
  const host = req.headers.get("host") ?? "";
  if (!HOSTS.has(host)) {
    return new NextResponse("Forbidden host", { status: 403 });
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    const origin = req.headers.get("origin");
    if (origin && !HOSTS.has(origin.replace(/^https?:\/\//, ""))) {
      return new NextResponse("Forbidden origin", { status: 403 });
    }
    if (!(req.headers.get("content-type") ?? "").startsWith("application/json")) {
      return new NextResponse("JSON only", { status: 415 });
    }
  }
  return NextResponse.next();
}

export const config = { matcher: "/api/:path*" };
