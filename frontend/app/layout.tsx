import type { Metadata } from "next";
import { Geist, Geist_Mono, Outfit, JetBrains_Mono, Arimo } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
// Landing-page typefaces (Stitch "Yosy Project AI Identity Edition"):
// Outfit for display/body, Arimo for labels/chips, JetBrains Mono for metrics.
const outfit = Outfit({ variable: "--font-outfit", subsets: ["latin"], weight: ["300", "400", "500", "600", "700"] });
const jetbrainsMono = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"], weight: ["400", "500"] });
const arimo = Arimo({ variable: "--font-arimo", subsets: ["latin"], weight: ["400", "500", "600", "700"] });

export const metadata: Metadata = {
  title: "CDSS AI Keperawatan",
  description: "Sistem Pendukung Keputusan Klinis Berbasis Standar 3S & 3N.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id" className={`dark ${geistSans.variable} ${geistMono.variable} ${outfit.variable} ${jetbrainsMono.variable} ${arimo.variable} h-full`}>
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
        />
      </head>
      <body className="min-h-full antialiased">{children}</body>
    </html>
  );
}
