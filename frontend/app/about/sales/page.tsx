'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { 
  Shield, Heart, Target, Layers, Rss, Zap, 
  Sparkles, Globe, Rocket, Users, Lightbulb,
  ArrowRight, MousePointer2
} from 'lucide-react';
import PageWrapper from '@/components/layout/PageWrapper';
import { Badge } from '@/components/ui/badge';

// Reusable Section component with the "Pro" glow aesthetic
interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  gradient: string;
}

const Section: React.FC<SectionProps> = ({ title, icon, children, gradient }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true }}
    transition={{ duration: 0.5 }}
    className={`p-8 rounded-2xl bg-slate-900/40 border ${gradient} backdrop-blur-2xl shadow-[0_0_25px_rgba(59,130,246,0.2)] transition-all duration-500 hover:scale-[1.01] hover:shadow-[0_0_50px_rgba(59,130,246,0.4)]`}
  >
    <div className="flex items-center gap-4 mb-6">
      <div className="group relative">
        {icon}
        <div className="absolute inset-0 scale-0 group-hover:scale-110 transition-transform duration-300 origin-center opacity-0 group-hover:opacity-40 bg-blue-400/20 rounded-full"></div>
      </div>
      <h2 className="text-2xl font-bold text-slate-50 mb-0 font-sans tracking-tight">{title}</h2>
    </div>
    <div className="prose prose-invert prose-lg max-w-none text-slate-200 font-sans leading-relaxed space-y-5">
      {children}
    </div>
  </motion.div>
);

const SimpleAboutPage: React.FC = () => {
  return (
    <PageWrapper>
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="space-y-16 py-12">

          {/* VISIONARY HERO HEADER */}
          <motion.div 
            className="flex flex-col items-center text-center space-y-8"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
          >
            <div className="p-5 rounded-3xl bg-gradient-to-br from-blue-500/30 via-cyan-400/20 to-indigo-500/30 backdrop-blur-3xl border border-blue-400/50 shadow-[0_0_60px_rgba(59,130,246,0.4)]">
              <Sparkles className="h-14 w-14 text-blue-200 animate-pulse" />
            </div>
            
            <div className="space-y-4">
              <h1 className="text-5xl sm:text-6xl md:text-7xl font-black font-sans tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-blue-100 via-blue-300 to-indigo-200 drop-shadow-sm">
                AI for the Independent Mind
              </h1>
              <p className="text-2xl md:text-3xl text-blue-300/80 font-sans font-light max-w-3xl mx-auto leading-tight italic">
                Bridging the gap between elite technology and human-scale innovation.
              </p>
            </div>

            <div className="flex flex-wrap gap-3 justify-center">
              <Badge variant="outline" className="bg-blue-600/20 text-blue-300 border-blue-500/40 px-4 py-1 text-sm">
                Democratic Innovation
              </Badge>
              <Badge variant="outline" className="bg-indigo-600/20 text-indigo-300 border-indigo-500/40 px-4 py-1 text-sm">
                Cognitive Freedom
              </Badge>
              <Badge variant="outline" className="bg-cyan-600/20 text-cyan-300 border-cyan-500/40 px-4 py-1 text-sm">
                Human-Centric Design
              </Badge>
            </div>
            
            <div className="w-32 h-1.5 bg-gradient-to-r from-transparent via-blue-500 to-transparent rounded-full opacity-50"></div>
          </motion.div>

          {/* CORE MISSION */}
          <Section
            title="Our Mission: Empowering the 100%"
            icon={<Target className="w-9 h-9 text-blue-400" />}
            gradient="border-blue-400/40 hover:border-blue-300/60"
          >
            <p>
              In a world where AI is often kept behind the gates of massive corporations, we are building a <strong>public utility for intelligence</strong>. Our mission is to take the most sophisticated analytical tools on the planet and place them directly into the hands of the individuals who need them most: creators, small business owners, and local leaders.
            </p>
            <p>
              We don&apos;t just provide software; we provide <strong>clarity</strong>. By transforming raw, overwhelming data into actionable insight, we enable you to compete at the highest level without the corporate overhead.
            </p>
          </Section>

          {/* THE OPPORTUNITY */}
          <Section
            title="The Vision: Your Cognitive Competitive Edge"
            icon={<Rocket className="w-9 h-9 text-indigo-400" />}
            gradient="border-indigo-400/40 hover:border-indigo-300/60"
          >
            <p>
              Imagine a world where your team can digest thousands of global signals instantly. We make that a reality. Our platform acts as your <strong>digital scout</strong>, finding the signal in the noise and preparing you for what&apos;s next.
            </p>
            <div className="grid md:grid-cols-3 gap-6 mt-8">
              <div className="bg-blue-900/10 border border-blue-500/20 p-5 rounded-xl">
                <Globe className="h-7 w-7 text-blue-400 mb-3" />
                <h4 className="font-bold text-white mb-2">Global Awareness</h4>
                <p className="text-sm text-slate-300">Access insights from across the world, translated and analyzed for immediate impact.</p>
              </div>
              <div className="bg-indigo-900/10 border border-indigo-500/20 p-5 rounded-xl">
                <Lightbulb className="h-7 w-7 text-indigo-400 mb-3" />
                <h4 className="font-bold text-white mb-2">Creative Velocity</h4>
                <p className="text-sm text-slate-300">Turn ideas into published reality in seconds, not days, with AI as your creative partner.</p>
              </div>
              <div className="bg-cyan-900/10 border border-cyan-500/20 p-5 rounded-xl">
                <Users className="h-7 w-7 text-cyan-400 mb-3" />
                <h4 className="font-bold text-white mb-2">Radical Reach</h4>
                <p className="text-sm text-slate-300">Small teams now have the publishing power and analytical depth of major media labs.</p>
              </div>
            </div>
          </Section>

          {/* THE REALITY SECTION */}
          <Section
            title="The Reality: Information Integrity"
            icon={<Shield className="w-9 h-9 text-cyan-400" />}
            gradient="border-cyan-400/40 hover:border-cyan-300/60"
          >
            <p>
              The digital landscape is becoming flooded with "synthetic" content. Our system works tirelessly in the background to <strong>verify, validate, and clarify</strong> every piece of information you see.
            </p>
            <p>
              We use a sophisticated "Extract-Translate-Load" (ETL) pipeline that ensures what you read is grounded in fact. We strip away the bias and the fluff, leaving you with the <strong>pure intelligence</strong> you need to make decisions with confidence.
            </p>
            <div className="mt-6 p-6 bg-slate-800/40 rounded-2xl border border-slate-700/50 italic text-blue-200">
              "Our technology doesn't just process information; it protects the human element in information."
            </div>
          </Section>

          {/* THE FUTURE SECTION */}
          <Section
            title="Possibilities Without Borders"
            icon={<Zap className="w-9 h-9 text-amber-400" />}
            gradient="border-amber-400/40 hover:border-amber-300/60"
          >
            <p>
              We are entering a new era of <strong>Human-AI Collaboration</strong>. Our platform is the bridge to that future. Whether you are building a boutique brand, leading a community movement, or researching the next breakthrough, we provide the infrastructure for your imagination.
            </p>
            <ul className="space-y-4 mt-6">
              <li className="flex gap-4 items-start">
                <div className="mt-1.5 h-2 w-2 rounded-full bg-blue-400 shadow-[0_0_10px_rgba(96,165,250,0.8)]" />
                <span><strong>Hyper-Personalized Intelligence:</strong> Tailored feeds that learn what matters to your specific mission.</span>
              </li>
              <li className="flex gap-4 items-start">
                <div className="mt-1.5 h-2 w-2 rounded-full bg-indigo-400 shadow-[0_0_10px_rgba(129,140,248,0.8)]" />
                <span><strong>Instant Global Publishing:</strong> Share your vision with a professional-grade platform that handles the complexity for you.</span>
              </li>
              <li className="flex gap-4 items-start">
                <div className="mt-1.5 h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.8)]" />
                <span><strong>Trust by Default:</strong> Built-in forensic tools that ensure your audience knows your content is authentic and rigorous.</span>
              </li>
            </ul>
          </Section>

          {/* CALL TO ACTION */}
          <motion.div 
            className="relative overflow-hidden bg-gradient-to-br from-blue-600/20 via-indigo-600/10 to-transparent border border-blue-400/30 rounded-3xl p-12 text-center"
            initial={{ opacity: 0, scale: 0.98 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
          >
            <div className="absolute top-0 left-0 w-64 h-64 bg-blue-500/10 rounded-full blur-[80px] -translate-x-1/2 -translate-y-1/2"></div>
            <div className="absolute bottom-0 right-0 w-64 h-64 bg-indigo-500/10 rounded-full blur-[80px] translate-x-1/2 translate-y-1/2"></div>

            <div className="relative z-10 space-y-8">
              <div className="space-y-4">
                <h3 className="text-3xl md:text-4xl font-bold text-slate-50 font-sans tracking-tight">
                  Stop Reacting. Start Innovating.
                </h3>
                <p className="text-xl text-slate-300 font-sans max-w-2xl mx-auto leading-relaxed">
                  Join a community of pioneers who are using the A.R.C. Framework to reclaim their time and amplify their impact.
                </p>
              </div>

              <div className="flex flex-wrap gap-5 justify-center">
                <a 
                  href="/publish" 
                  className="group flex items-center gap-2 px-10 py-5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold rounded-2xl shadow-[0_0_20px_rgba(37,99,235,0.4)] hover:shadow-[0_0_40px_rgba(37,99,235,0.6)] transition-all duration-300 text-lg"
                >
                  Join the Expedition <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
                </a>
                <a 
                  href="mailto:sales@arc-codex.com"
                  className="flex items-center gap-2 px-10 py-5 bg-slate-800/80 hover:bg-slate-700 text-slate-200 font-bold rounded-2xl border border-slate-600/50 transition-all duration-300 text-lg"
                >
                  sales@arc-codex.com
                </a>
              </div>
            </div>
          </motion.div>

          {/* FOOTER */}
          <footer className="text-center text-sm text-slate-500 pt-8 pb-4 border-t border-slate-800/50">
            <p className="font-sans tracking-wide">
              © {new Date().getFullYear()} Arc Codex. Empowering the next generation of independent thinkers.
            </p>
          </footer>

        </div>
      </div>
    </PageWrapper>
  );
};

export default SimpleAboutPage;
