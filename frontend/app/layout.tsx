import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ClarityAI — Business Research Assistant",
  description: "AI-powered business intelligence through collaborative multi-agent reasoning.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
