// File: app/layout.tsx
import { Ubuntu } from 'next/font/google';
import './globals.css';
import ClientLayout from './ClientLayout';

const fontUbuntu = Ubuntu({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-sans" });

export const metadata = {
  title: 'Arc Codex',
  description: 'AI-powered news intelligence with A.R.C. analysis — Facts Only, Executive Summary, and Full Take on every story.',
  metadataBase: new URL('https://arc-codex.com'),
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={fontUbuntu.variable}>
        <ClientLayout>
          {children}
        </ClientLayout>
      </body>
    </html>
  );
}
