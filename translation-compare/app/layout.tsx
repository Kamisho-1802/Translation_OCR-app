import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "翻訳API比較",
  description: "Azure Translator と DeepL の翻訳品質を並べて比較する検証用アプリ",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
