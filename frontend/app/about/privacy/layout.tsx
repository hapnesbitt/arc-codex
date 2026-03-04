// Filename: /frontend/app/about/privacy/layout.tsx
// Privacy Policy metadata
import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Privacy Policy | Arc Codex',
  description: 'Arc Codex privacy policy: commitment to user privacy, minimal data collection, and no advertising or tracking.',
  keywords: [
    'Arc Codex privacy',
    'privacy policy',
    'data protection',
    'user privacy',
    'no ads',
    'no tracking'
  ],
  robots: 'index, follow',
  openGraph: {
    title: 'Privacy Policy | Arc Codex',
    description: 'Our commitment to protecting your privacy and data.',
    type: 'website',
  },
};

export default function PrivacyLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
