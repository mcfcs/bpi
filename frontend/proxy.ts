import { NextResponse, type NextRequest } from "next/server";

/**
 * Two optional guards for a hosted demo (see README.md). Both are off unless their variable is set, so
 * local development and tests are unchanged.
 *
 * - DEMO_BASIC_AUTH="user:password": every page and every /api call asks for it with HTTP basic auth,
 *   so a shared link can't be used by anyone who finds it. Proxy runs before the /api rewrite in
 *   next.config.mjs, so the backend is covered too.
 * - BACKEND_SHARED_SECRET: added as X-Demo-Key to every /api request forwarded to the backend. When the
 *   backend has its own public URL (option D), it refuses requests without the key, so nobody can skip
 *   this password by calling the backend directly.
 */
export function proxy(request: NextRequest) {
  const expected = process.env.DEMO_BASIC_AUTH;
  if (expected && !hasPassword(request, expected)) {
    return new NextResponse("Password required", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="ALAMKansya demo", charset="UTF-8"' },
    });
  }
  const key = process.env.BACKEND_SHARED_SECRET;
  if (key && request.nextUrl.pathname.startsWith("/api/")) {
    const headers = new Headers(request.headers);
    headers.set("x-demo-key", key);
    return NextResponse.next({ request: { headers } });
  }
  return NextResponse.next();
}

function hasPassword(request: NextRequest, expected: string): boolean {
  const [scheme, encoded] = (request.headers.get("authorization") ?? "").split(" ");
  if (scheme !== "Basic" || !encoded) return false;
  try {
    return atob(encoded) === expected;
  } catch {
    return false;
  }
}

export const config = {
  // Static build files and the favicon need no password.
  matcher: "/((?!_next/static|_next/image|icon.svg).*)",
};
