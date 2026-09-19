import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Third Participant | Voice Call Intelligence",
  description: "Realtime conversation intelligence, disagreement detection, fact checking, and post-call reports.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#090d16] text-slate-100 antialiased selection:bg-indigo-500 selection:text-white">
        {children}
      </body>
    </html>
  );
}
