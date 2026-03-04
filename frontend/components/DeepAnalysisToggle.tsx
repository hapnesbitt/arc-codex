// File: components/DeepAnalysisToggle.tsx
'use client';
import React, { ReactNode } from 'react';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface DeepAnalysisToggleProps {
  children: ReactNode;
}

function DeepAnalysisToggle({ children }: DeepAnalysisToggleProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger
        className="flex items-center justify-center gap-2 cursor-pointer text-amber-400 hover:text-amber-300 hover:bg-slate-800/50 transition-colors p-2 rounded-lg font-semibold select-none"
      >
        <span>{isOpen ? 'Hide Deep Analysis' : 'Show Deep Analysis'}</span>
        {isOpen ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
      </CollapsibleTrigger>
      <CollapsibleContent className="overflow-hidden pt-4">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default React.memo(DeepAnalysisToggle);
