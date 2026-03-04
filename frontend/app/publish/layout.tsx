// Filename: /frontend/app/publish/layout.tsx
import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Publish | Arc Codex A.R.C.',
  description: 'Submit a URL, text, or file for A.R.C. cognitive analysis. PII redaction enabled.',
  openGraph: {
    title: 'Publish | Arc Codex A.R.C.',
    description: 'Transform your ideas with A.R.C. cognitive analysis',
    type: 'website',
  },
};

export default function PublishLayout({ children }: { children: React.ReactNode }) {
  return children;
}
