import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";

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
          <Link
            className="text-zinc-50 font-bold relative top-4 left-4 cursor-pointer"
            href="/"
          >
            LINE AI
          </Link>
        </h1>
        <main>{children}</main>
      </body>
    </html>
  );
}
