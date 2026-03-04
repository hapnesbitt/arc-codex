// File: components/ContentStats.tsx
import React from 'react';
import { motion } from "framer-motion";
import { Zap } from "lucide-react";

interface ContentStatsProps {
  wordCount?: number;
  charCount?: number;
}

function ContentStats({ wordCount = 0, charCount = 0 }: ContentStatsProps) {
  const minRead = Math.ceil(wordCount / 200) || 1;
  return (
    <motion.div
      initial={{ x: 20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ delay: 0.4 }}
    >
      <div className="border border-yellow-500/20 bg-slate-900/30 backdrop-blur-xl rounded-lg">
        <div className="p-4">
          <div className="flex items-center gap-2 text-xl text-yellow-400 mb-4">
            <Zap className="h-5 w-5" />
            <span>Content Stats</span>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <motion.div
              className="text-center p-3 bg-purple-600/10 border border-purple-500/30 rounded-lg"
              whileHover={{ scale: 1.05 }}
            >
              <div className="text-2xl font-bold text-purple-300">{wordCount}</div>
              <div className="text-xs text-purple-400">Words</div>
            </motion.div>
            <motion.div
              className="text-center p-3 bg-blue-600/10 border border-blue-500/30 rounded-lg"
              whileHover={{ scale: 1.05 }}
            >
              <div className="text-2xl font-bold text-blue-300">{charCount}</div>
              <div className="text-xs text-blue-400">Characters</div>
            </motion.div>
            <motion.div
              className="text-center p-3 bg-green-600/10 border border-green-500/30 rounded-lg"
              whileHover={{ scale: 1.05 }}
            >
              <div className="text-2xl font-bold text-green-300">{minRead}</div>
              <div className="text-xs text-green-400">Min Read</div>
            </motion.div>
            <motion.div
              className="text-center p-3 bg-yellow-600/10 border border-yellow-500/30 rounded-lg"
              whileHover={{ scale: 1.05 }}
            >
              <div className="text-2xl font-bold text-yellow-300">A+</div>
              <div className="text-xs text-yellow-400">AI Ready</div>
            </motion.div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export default React.memo(ContentStats);
