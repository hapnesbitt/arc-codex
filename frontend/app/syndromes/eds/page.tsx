// Filename: /frontend/app/syndromes/eds/page.tsx
// Condition Intelligence Unit: Ehlers-Danlos Syndrome
// v3.0 Apr 20 2026 — Refined for Clinical Gravity & Epistemic Responsibility

import type { Metadata } from 'next';
import Link from 'next/link';
import { 
  BookOpen, Play, GraduationCap, 
  ExternalLink, Activity, Microscope, 
  ChevronRight, Info 
} from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';

export const metadata: Metadata = {
  title: 'Ehlers-Danlos Syndrome (EDS) // Intelligence Unit',
  description: 'A forensic exploration of connective tissue disorders, clinical criteria, and diagnostic pathways.',
};

const SectionHeader = ({ icon: Icon, label, protocol }: { icon: any, label: string, protocol: string }) => (
  <div className="flex flex-col gap-2 mb-8">
    <div className="flex items-center gap-3">
      <Icon className="h-4 w-4 text-slate-400" />
      <h2 className="text-sm font-mono uppercase tracking-[0.4em] text-slate-500">{label}</h2>
    </div>
    <div className="text-[9px] font-mono text-slate-300 uppercase tracking-widest italic">Protocol // {protocol}</div>
  </div>
);

export default function EDSIntelligenceUnit() {
  return (
    <PageWrapper>
      <div className="min-h-screen bg-[#fdfbf7] text-slate-900 font-ubuntu selection:bg-slate-900 selection:text-white">
        <main className="max-w-6xl mx-auto px-8 py-24 md:py-40">
          
          {/* THE CLINICAL HEADER */}
          <header className="max-w-3xl mb-32 space-y-8">
            <div className="flex items-center gap-4 text-[10px] font-mono uppercase tracking-[0.5em] text-slate-400">
              <Activity className="h-3 w-3" /> Connective Tissue // Heritable
            </div>
            <h1 className="text-6xl md:text-8xl font-bold tracking-tighter leading-none italic">
              Ehlers-Danlos <br /> 
              <span className="text-slate-300 font-normal">Syndrome.</span>
            </h1>
            <div className="h-px w-24 bg-slate-900" />
            <p className="text-xl md:text-2xl text-slate-500 italic leading-relaxed font-light">
              &ldquo;A systemic failure of the body&apos;s architectural scaffolding. 
              Thirteen subtypes identified; one common clinical mystery.&rdquo;
            </p>
          </header>

          {/* THE INTELLIGENCE GRID */}
          <div className="grid lg:grid-cols-2 gap-px bg-slate-200 border border-slate-200">
            
            {/* I. THE READ SECTOR */}
            <section className="bg-[#fdfbf7] p-12 space-y-8">
              <SectionHeader icon={BookOpen} label="Observation" protocol="FORENSIC_LITERATURE" />
              <div className="space-y-6">
                <p className="text-slate-600 leading-relaxed italic font-light text-lg">
                  EDS is a collection of genetic disorders affecting collagen synthesis. 
                  The hypermobile subtype (hEDS) remains the only variant without 
                  a confirmed biomarker, requiring a rigorous clinical appraisal.
                </p>
                <a 
                  href="https://arc-codex.com/article/eb3f80dec719303ff9b53f47d8aac170"
                  className="group flex flex-col justify-between p-8 border border-slate-200 hover:border-slate-900 transition-all duration-500 min-h-[160px]"
                >
                  <h3 className="text-xl font-bold italic group-hover:text-blue-700 transition-colors">
                    The Mayo Clinic Overview
                  </h3>
                  <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-widest">A.R.C. Analysis Included</span>
                    <ExternalLink className="h-3 w-3 text-slate-300 group-hover:text-slate-900" />
                  </div>
                </a>
              </div>
            </section>

            {/* II. THE WATCH SECTOR */}
            <section className="bg-[#fdfbf7] p-12 space-y-8">
              <SectionHeader icon={Play} label="Visualization" protocol="DIAGNOSTIC_MEDIA" />
              <div className="space-y-6">
                <p className="text-slate-600 leading-relaxed italic font-light text-lg">
                  Clinical insights from the Department of Clinical Genomics. 
                  Dr. David Deyle outlines the diagnostic red flags and systemic impact.
                </p>
                <div className="aspect-video bg-slate-100 border border-slate-200 overflow-hidden group relative">
                   <iframe
                    src="https://www.youtube.com/embed/kEB4Z6CrH-k"
                    className="w-full h-full grayscale hover:grayscale-0 transition-all duration-700"
                    title="EDS Overview"
                  />
                  <div className="absolute bottom-0 w-full p-4 bg-white/90 backdrop-blur-sm flex justify-between items-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <span className="text-[9px] font-mono uppercase tracking-widest text-slate-500">Mayo Clinic // Genomic Analysis</span>
                  </div>
                </div>
              </div>
            </section>

            {/* III. THE LEARN SECTOR */}
            <section className="bg-[#fdfbf7] p-12 space-y-8">
              <SectionHeader icon={GraduationCap} label="Pedagogy" protocol="SCHOOL_OF_CHAT" />
              <div className="space-y-6">
                <p className="text-slate-600 leading-relaxed italic font-light text-lg">
                  Formal assessment of condition management. Test your understanding of 
                  Beighton Scores, comorbidities, and the diagnostic path.
                </p>
                <a 
                  href="https://soc.arc-codex.com/category/health-medical"
                  className="group flex flex-col justify-between p-8 border border-slate-200 hover:border-slate-900 transition-all duration-500 min-h-[160px]"
                >
                  <h3 className="text-xl font-bold italic group-hover:text-purple-700 transition-colors">
                    EDS Awareness Curriculum
                  </h3>
                  <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-widest">AI-Graded Assessment</span>
                    <ChevronRight className="h-3 w-3 text-slate-300 group-hover:translate-x-1 group-hover:text-slate-900 transition-all" />
                  </div>
                </a>
              </div>
            </section>

            {/* IV. EXTERNAL AUTHORITY (The "Additional Links") */}
            <section className="bg-[#fdfbf7] p-12 space-y-8">
              <SectionHeader icon={Microscope} label="Reference" protocol="EXTERNAL_REGISTRY" />
              <div className="space-y-4">
                {[
                  { label: 'The Ehlers-Danlos Society', href: 'https://www.ehlers-danlos.com/' },
                  { label: 'ICD-10-CM Registry', href: 'https://www.icd10data.com/ICD10CM/Codes/M00-M99/M30-M36/M35/M35.7' },
                  { label: 'Wikipedia // Hypermobility Spectrum', href: 'https://en.wikipedia.org/wiki/Hypermobility_spectrum_disorder' }
                ].map((ref) => (
                  <a 
                    key={ref.label}
                    href={ref.href}
                    target="_blank"
                    className="flex items-center justify-between p-4 border border-slate-100 hover:border-slate-300 text-sm font-mono uppercase tracking-widest text-slate-500 hover:text-slate-900 transition-all group"
                  >
                    {ref.label} <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </a>
                ))}
              </div>
            </section>

          </div>

          {/* THE DISCLAIMER */}
          <footer className="mt-40 space-y-12">
            <div className="max-w-2xl mx-auto p-8 border border-slate-200 flex gap-6 items-start">
              <Info className="h-5 w-5 text-slate-300 shrink-0 mt-1" />
              <p className="text-xs text-slate-400 font-ubuntu italic leading-relaxed">
                <strong>Forensic Notice:</strong> This intelligence unit is provided for information purposes within the A.R.C. Framework. 
                It does not constitute medical advice. Consult with a clinical geneticist or rheumatologist for diagnostic verification.
              </p>
            </div>
            <p className="text-center text-[10px] font-mono uppercase tracking-[0.8em] opacity-30">
               A.R.C. CODEX // HEALTH & MEDICAL // 2026
            </p>
          </footer>

        </main>
      </div>
    </PageWrapper>
  );
}
