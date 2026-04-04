// File: components/StatusMessage.tsx
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle, XCircle, Loader, Info } from 'lucide-react';

type Status = 'success' | 'error' | 'loading' | 'idle';

interface StatusMessageProps {
  status: Status;
  message: string;
}

function StatusMessage({ status, message }: StatusMessageProps) {
  if (!message) return null;

  const ICONS: Record<Status, React.ReactNode> = {
    success: <CheckCircle aria-hidden="true" className="h-5 w-5 flex-shrink-0" />,
    error:   <XCircle    aria-hidden="true" className="h-5 w-5 flex-shrink-0" />,
    loading: <Loader     aria-hidden="true" className="h-5 w-5 animate-spin flex-shrink-0" />,
    idle:    <Info       aria-hidden="true" className="h-5 w-5 flex-shrink-0" />,
  };

  const STYLES: Record<Status, string> = {
    success: 'bg-green-600/10 border-green-500/30 text-green-300',
    error:   'bg-red-600/10 border-red-500/30 text-red-300',
    loading: 'bg-blue-600/10 border-blue-500/30 text-blue-300',
    idle:    'bg-blue-600/10 border-blue-500/30 text-blue-300',
  };

  // errors interrupt immediately; everything else is polite
  const role     = status === 'error' ? 'alert'  : 'status';
  const ariaLive = status === 'error' ? 'assertive' : 'polite';

  const icon  = ICONS[status]  ?? ICONS.idle;
  const style = STYLES[status] ?? STYLES.idle;

  return (
    <AnimatePresence>
      <motion.div
        role={role}
        aria-live={ariaLive}
        aria-atomic="true"
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
