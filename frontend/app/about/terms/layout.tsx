// Filename: /frontend/app/about/terms/layout.tsx
import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Terms of Service | Arc Codex',
  description: 'Arc Codex terms of service: user guidelines, content policies, intellectual property rights, and community standards.',
  robots: 'index, follow',
  openGraph: {
    title: 'Terms of Service | Arc Codex',
    description: 'Terms and conditions for using the Arc Codex platform.',
    type: 'website',
  },
};

export default function TermsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
