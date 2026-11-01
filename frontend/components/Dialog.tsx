'use client';

import React from 'react';
import { X } from 'lucide-react';
import { ApiError } from '../lib/api';

interface DialogProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}

/** Small modal used by confirm dialogs and pickers; matches the studio look. */
export function Dialog({ title, onClose, children, wide }: DialogProps) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`w-full ${wide ? 'max-w-3xl' : 'max-w-md'} max-h-[90vh] overflow-y-auto bg-white dark:bg-[#0B0F19] text-[#1F1A18] dark:text-white rounded-3xl border border-[#EDE6DD] dark:border-white/10 shadow-2xl p-6 space-y-4`}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="w-8 h-8 rounded-full border border-[#EDE6DD] dark:border-white/10 flex items-center justify-center text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-white cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export const btnPrimary =
  'inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-[#F26D5B] hover:bg-[#E05C4A] text-white text-xs font-bold transition-all shadow-md shadow-[#F26D5B]/20 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed';
export const btnSecondary =
  'inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-white dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-xs font-bold text-[#5C5047] dark:text-slate-300 hover:bg-[#FAF8F5] dark:hover:bg-white/10 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed';
export const btnDanger =
  'inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed';
export const inputCls =
  'w-full px-3.5 py-2 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-xs sm:text-sm text-[#1F1A18] dark:text-white focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30';
export const labelCls = 'block text-xs font-bold text-[#5C5047] dark:text-slate-300 mb-1.5';

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-700 dark:text-rose-400 text-xs font-semibold">
      {message}
    </div>
  );
}

export const errorMessage = (e: unknown) =>
  e instanceof ApiError && e.status === 401
    ? 'Your login has expired. Log in again (top right) and retry; your draft is saved.'
    : e instanceof Error
      ? e.message
      : 'Something went wrong. Please try again.';
