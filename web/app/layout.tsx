import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Line AI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased`}>
        <h1>
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a
            className="text-zinc-50 font-bold relative top-4 left-4 cursor-pointer hover:text-line transition-colors"
            href="/"
          >
            LINE AI
          </a>
        </h1>
        <main>{children}</main>
      </body>
    </html>
  );
}
