import React, { ReactNode } from 'react';
import { motion } from 'framer-motion';

interface ContentTabsProps {
  activeTab: string;
  setActiveTab: (tabId: string) => void;
  children: ReactNode;
}

const TABS = [
  { id: 'text', label: 'Write Content' },
  { id: 'upload', label: 'Use Uploaded File' },
];

const ContentTabs: React.FC<ContentTabsProps> = ({ activeTab, setActiveTab, children }) => {
  return (
    <div>
      <div className="flex border-b border-slate-700">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`relative px-4 py-2 text-lg font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-green-400'
                : 'text-slate-400 hover:text-green-400/80'
            }`}
          >
            {tab.label}
            {activeTab === tab.id && (
              <motion.div
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-green-400"
                layoutId="underline"
              />
            )}
          </button>
        ))}
      </div>
      <div className="py-6">{children}</div>
    </div>
  );
};

export default React.memo(ContentTabs);

