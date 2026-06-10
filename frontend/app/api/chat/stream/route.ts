import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();

  const upstream = await fetch(`${BACKEND}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!upstream.ok) {
    return new Response(
      JSON.stringify({ error: "Backend request failed" }),
      { status: upstream.status, headers: { "Content-Type": "application/json" } }
    );
  }

  // Proxy the SSE stream through to the browser
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
