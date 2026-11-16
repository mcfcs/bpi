import { NextResponse, type NextRequest } from "next/server";

/**
 * Adds BACKEND_SHARED_SECRET as X-Demo-Key to every /api request forwarded to the backend (see README.md).
 * The backend has its own public URL on Render and refuses requests without the key, so it can only be
 * used through this site. Off unless the variable is set, so local development is unchanged.
 */
export function proxy(request: NextRequest) {
  const key = process.env.BACKEND_SHARED_SECRET;
  if (!key) return NextResponse.next();
  const headers = new Headers(request.headers);
  headers.set("x-demo-key", key);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  // Proxy runs before the /api rewrite in next.config.mjs, so the header reaches the backend.
  matcher: "/api/:path*",
};
