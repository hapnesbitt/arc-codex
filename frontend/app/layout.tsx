// File: app/layout.tsx
import type { Metadata, Viewport } from 'next';
import { Literata, Public_Sans } from 'next/font/google';
import './globals.css';
import ClientLayout from './ClientLayout';
import ServiceWorkerRegistration from '@/components/ServiceWorkerRegistration';

const fontSerif = Literata({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});

const fontSans = Public_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: 'Arc Codex',
  description: 'AI-powered news intelligence with A.R.C. analysis — Facts Only, Executive Summary, and Full Take on every story.',
  metadataBase: new URL('https://arc-codex.com'),

  manifest: '/manifest.json',

  alternates: {
    types: {
      'application/opensearchdescription+xml': '/opensearch.xml',
      'application/rss+xml': '/rss.xml',
    },
  },

  icons: {
    icon: '/favicon.ico',
    apple: [
      { url: '/icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' },
    ],
  },

  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Arc Codex',
  },
};

export const viewport: Viewport = {
  themeColor: '#f59e0b',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${fontSerif.variable} ${fontSans.variable}`}>
      <body>
        <ClientLayout>
          {children}
        </ClientLayout>
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
