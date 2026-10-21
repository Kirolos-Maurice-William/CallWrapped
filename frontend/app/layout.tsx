import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CALLWRAPPED // Live Voice Referee",
  description:
    "Consensual voice fact-checking and post-call intelligence for Discord.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#090a0d] text-[#e6e8ee] antialiased selection:bg-[#3b82f6] selection:text-white">
        {children}
      </body>
    </html>
  );
}
