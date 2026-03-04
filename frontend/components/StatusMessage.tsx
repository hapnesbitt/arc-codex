// File: components/StatusMessage.tsx
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle, XCircle, Loader, Info } from 'lucide-react';

type Status = 'success' | 'error' | 'loading' | 'idle';

interface StatusMessageProps {
  status: Status;
  message: string;
}

// This component maps the "status" string directly to an icon and style.
function StatusMessage({ status, message }: StatusMessageProps) {
  if (!message) return null;

  const ICONS: Record<Status, React.ReactNode> = {
    success: <CheckCircle className="h-5 w-5" />,
    error: <XCircle className="h-5 w-5" />,
    loading: <Loader className="h-5 w-5 animate-spin" />,
    idle: <Info className="h-5 w-5" />,
  };

  const STYLES: Record<Status, string> = {
    success: 'bg-green-600/10 border-green-500/30 text-green-300',
    error: 'bg-red-600/10 border-red-500/30 text-red-300',
    loading: 'bg-blue-600/10 border-blue-500/30 text-blue-300',
    idle: 'bg-blue-600/10 border-blue-500/30 text-blue-300',
  };

  // Fallback to 'idle' icon if status is unrecognized
  const icon = ICONS[status] || ICONS.idle;
  const style = STYLES[status] || STYLES.idle;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 10, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -10, scale: 0.95 }}
        className={`flex items-center gap-3 p-4 rounded-xl border ${style}`}
      >
        {icon}
        <div className="text-sm font-medium">{message}</div>
      </motion.div>
    </AnimatePresence>
  );
}

export default React.memo(StatusMessage);
