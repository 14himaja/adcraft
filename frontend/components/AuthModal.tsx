'use client';

import React from 'react';
import { X } from 'lucide-react';
import { AuthForm } from './AuthForm';
import { UserProfile } from '../lib/api';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialMode?: 'login' | 'register';
  onSuccess?: (user?: UserProfile) => void;
}

export function AuthModal({
  isOpen,
  onClose,
  initialMode = 'login',
  onSuccess,
}: AuthModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-md">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute -top-12 right-0 w-9 h-9 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors cursor-pointer"
          aria-label="Close authentication"
        >
          <X className="w-5 h-5" />
        </button>

        <AuthForm
          initialMode={initialMode}
          onSuccess={(user) => {
            if (onSuccess) onSuccess(user);
            onClose();
          }}
        />
      </div>
    </div>
  );
}

export default AuthModal;
