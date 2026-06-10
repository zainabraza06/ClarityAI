import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const upstream = await fetch(`${BACKEND}/api/documents/${params.id}`, {
    method: "DELETE",
  });

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
