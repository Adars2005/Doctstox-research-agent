import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Docstox-research agent",
  description: "Evidence-driven AI equity research agent",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
