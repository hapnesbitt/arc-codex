import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Contact | Arc Codex',
  description: 'Get in touch with the Arc Codex founder.',
  robots: 'index, follow',
};

export default function ContactLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
