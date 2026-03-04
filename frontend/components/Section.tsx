// frontend/components/Section.tsx
import { ReactNode } from 'react';

interface SectionProps {
  title: string;
  icon: ReactNode;
  gradient: string;
  children: ReactNode;
}

export default function Section({ title, icon, gradient, children }: SectionProps) {
  return (
    <div className={`p-6 rounded-2xl border ${gradient} backdrop-blur-md mb-6`}>
      <div className="flex items-center gap-3 mb-4">
        {icon}
        <h2 className="text-xl font-bold text-slate-100">{title}</h2>
      </div>
      <div>{children}</div>
    </div>
  );
}
