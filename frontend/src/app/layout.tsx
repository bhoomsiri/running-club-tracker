import type { Metadata, Viewport } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { thTH } from "@clerk/localizations";
import { Noto_Sans_Thai } from "next/font/google";

import "./globals.css";

// Thai needs a font that actually has the glyphs — a latin-only face falls back to
// whatever the phone happens to have, and line heights end up all over the place.
const notoSansThai = Noto_Sans_Thai({
  variable: "--font-sans-thai",
  subsets: ["thai", "latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "ชมรมวิ่ง",
  description: "บันทึกระยะวิ่ง สะสมแต้ม แลกของรางวัล",
};

export const viewport: Viewport = {
  // Members are on phones. `viewportFit` keeps the bottom nav clear of the home
  // indicator on iPhones.
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <ClerkProvider localization={thTH}>
      <html lang="th" className={`${notoSansThai.variable} h-full antialiased`}>
        <body className="min-h-full flex flex-col bg-background text-foreground">
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
