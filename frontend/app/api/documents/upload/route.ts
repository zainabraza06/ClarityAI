import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const formData = await req.formData();

  const upstream = await fetch(`${BACKEND}/api/documents/upload`, {
    method: "POST",
    body: formData,
    // Do NOT set Content-Type — fetch sets it automatically with the multipart boundary
  });

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
