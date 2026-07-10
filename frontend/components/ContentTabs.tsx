import React, { ReactNode, useRef, useId } from 'react';
import { motion } from 'framer-motion';

interface ContentTabsProps {
  activeTab: string;
  setActiveTab: (tabId: string) => void;
  children: ReactNode;
}

const TABS = [
  { id: 'text',   label: 'Write Content' },
  { id: 'upload', label: 'Use Uploaded File' },
];

const ContentTabs: React.FC<ContentTabsProps> = ({ activeTab, setActiveTab, children }) => {
  const uid        = useId();
  const tabRefs    = useRef<(HTMLButtonElement | null)[]>([]);

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    if (e.key === 'ArrowRight') {
      const next = (index + 1) % TABS.length;
      setActiveTab(TABS[next].id);
      tabRefs.current[next]?.focus();
    } else if (e.key === 'ArrowLeft') {
      const prev = (index - 1 + TABS.length) % TABS.length;
      setActiveTab(TABS[prev].id);
      tabRefs.current[prev]?.focus();
    } else if (e.key === 'Home') {
      setActiveTab(TABS[0].id);
      tabRefs.current[0]?.focus();
    } else if (e.key === 'End') {
      setActiveTab(TABS[TABS.length - 1].id);
      tabRefs.current[TABS.length - 1]?.focus();
    }
  };

  return (
    <div>
      <div
        role="tablist"
        aria-label="Content input method"
        className="flex border-b border-slate-700"
      >
        {TABS.map((tab, index) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              ref={(el) => { tabRefs.current[index] = el; }}
              role="tab"
              id={`${uid}-tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`${uid}-panel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              className={`relative px-4 py-2 text-lg font-medium transition-colors outline-none
                ring-focus focus-visible:ring-inset ${
                isActive
                  ? 'text-green-400'
                  : 'text-slate-400 hover:text-green-400/80'
              }`}
            >
              {tab.label}
              {isActive && (
                <motion.div
                  className="absolute bottom-0 left-0 right-0 h-0.5 bg-green-400"
                  layoutId="underline"
                  aria-hidden="true"
                />
              )}
            </button>
          );
        })}
      </div>

      {TABS.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${uid}-panel-${tab.id}`}
          aria-labelledby={`${uid}-tab-${tab.id}`}
          hidden={activeTab !== tab.id}
          tabIndex={0}
          className="py-6 ring-focus rounded"
        >
          {activeTab === tab.id && children}
        </div>
      ))}
    </div>
  );
};

export default React.memo(ContentTabs);
