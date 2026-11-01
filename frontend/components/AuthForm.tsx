'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { login, register, UserProfile } from '../lib/api';
import { Sparkles, User, Mail, Lock, Eye, EyeOff, Building, ArrowRight, Loader2 } from 'lucide-react';

interface AuthFormProps {
  initialMode?: 'login' | 'register';
  onSuccess?: (user?: UserProfile) => void;
}

export function AuthForm({ initialMode = 'login', onSuccess }: AuthFormProps) {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'register'>(initialMode);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [workspaceName, setWorkspaceName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);
    setLoading(true);

    try {
      if (mode === 'login') {
        const profile = await login(email, password);
        if (onSuccess) {
          onSuccess(profile);
        } else {
          router.push('/settings/meta');
        }
      } else {
        await register(
          email,
          password,
          name.trim() || undefined,
          workspaceName.trim() || undefined
        );
        setSuccessMessage('Account created successfully! Please sign in with your password to continue.');
        setMode('login');
        setPassword('');
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md p-6 sm:p-8 bg-white dark:bg-[#111827]/90 backdrop-blur-xl border border-[#EDE6DD] dark:border-white/10 rounded-3xl shadow-xl dark:shadow-2xl text-[#1F1A18] dark:text-white transition-colors duration-200">
      {/* Brand Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#F26D5B] via-[#FF8E53] to-[#A855F7] flex items-center justify-center shadow-lg shadow-[#F26D5B]/20">
          <Sparkles className="w-5 h-5 text-white" />
        </div>
        <div>
          <h3 className="text-lg font-extrabold text-[#1F1A18] dark:text-white tracking-tight leading-none">
            {mode === 'login' ? 'Welcome Back' : 'Create Account'}
          </h3>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-1">
            {mode === 'login' ? 'Sign in to access your ad campaigns' : 'Get started with AI Instagram ad creation'}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#EDE6DD] dark:border-white/10 mb-6">
        <button
          type="button"
          onClick={() => {
            setMode('login');
            setError(null);
            setSuccessMessage(null);
            setShowPassword(false);
          }}
          className={`flex-1 pb-3 text-sm font-semibold text-center border-b-2 transition-all cursor-pointer ${
            mode === 'login'
              ? 'border-[#F26D5B] text-[#F26D5B]'
              : 'border-transparent text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-slate-200'
          }`}
          data-testid="tab-login"
        >
          Sign In
        </button>
        <button
          type="button"
          onClick={() => {
            setMode('register');
            setError(null);
            setSuccessMessage(null);
            setShowPassword(false);
          }}
          className={`flex-1 pb-3 text-sm font-semibold text-center border-b-2 transition-all cursor-pointer ${
            mode === 'register'
              ? 'border-[#F26D5B] text-[#F26D5B]'
              : 'border-transparent text-[#7A6C63] dark:text-slate-400 hover:text-[#1F1A18] dark:hover:text-slate-200'
          }`}
          data-testid="tab-register"
        >
          Create Account
        </button>
      </div>

      {successMessage && (
        <div
          role="status"
          className="mb-5 p-3.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-xs sm:text-sm rounded-xl flex items-center gap-2"
          data-testid="auth-success"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="mb-5 p-3.5 bg-rose-500/10 border border-rose-500/30 text-rose-700 dark:text-rose-300 text-xs sm:text-sm rounded-xl flex items-center justify-between gap-2"
          data-testid="auth-error"
        >
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0" />
            <span>{error}</span>
          </div>
          {mode === 'login' && (
            <button
              type="button"
              onClick={() => {
                setMode('register');
                setError(null);
                setSuccessMessage(null);
              }}
              className="text-xs font-bold underline hover:text-[#F26D5B] shrink-0 cursor-pointer transition-colors"
            >
              Sign Up
            </button>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {mode === 'register' && (
          <div>
            <label htmlFor="name" className="block text-xs font-semibold text-[#7A6C63] dark:text-slate-300 mb-1.5">
              Full name
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-[#9C8F85] dark:text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                id="name"
                name="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full pl-10 pr-3.5 py-2.5 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-sm text-[#1F1A18] dark:text-white placeholder-[#9C8F85] dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30 focus:border-[#F26D5B] transition-all"
                placeholder="Himaja Kadari"
              />
            </div>
          </div>
        )}

        <div>
          <label htmlFor="email" className="block text-xs font-semibold text-[#7A6C63] dark:text-slate-300 mb-1.5">
            Email address
          </label>
          <div className="relative">
            <Mail className="w-4 h-4 text-[#9C8F85] dark:text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full pl-10 pr-3.5 py-2.5 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-sm text-[#1F1A18] dark:text-white placeholder-[#9C8F85] dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30 focus:border-[#F26D5B] transition-all"
              placeholder="you@example.com"
            />
          </div>
        </div>

        <div>
          <label htmlFor="password" className="block text-xs font-semibold text-[#7A6C63] dark:text-slate-300 mb-1.5">
            Password
          </label>
          <div className="relative">
            <Lock className="w-4 h-4 text-[#9C8F85] dark:text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              id="password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              required
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full pl-10 pr-10 py-2.5 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-sm text-[#1F1A18] dark:text-white placeholder-[#9C8F85] dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30 focus:border-[#F26D5B] transition-all"
              placeholder="••••••••"
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-[#9C8F85] hover:text-[#1F1A18] dark:text-slate-400 dark:hover:text-slate-200 transition-colors cursor-pointer rounded-lg focus:outline-none focus:ring-1 focus:ring-[#F26D5B]"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              title={showPassword ? 'Hide password' : 'Show password'}
              data-testid="toggle-password-visibility"
            >
              {showPassword ? (
                <EyeOff className="w-4 h-4" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        {mode === 'register' && (
          <div>
            <label htmlFor="workspace" className="block text-xs font-semibold text-[#7A6C63] dark:text-slate-300 mb-1.5">
              Workspace name (optional)
            </label>
            <div className="relative">
              <Building className="w-4 h-4 text-[#9C8F85] dark:text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                id="workspace"
                name="workspace"
                type="text"
                value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)}
                className="w-full pl-10 pr-3.5 py-2.5 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-sm text-[#1F1A18] dark:text-white placeholder-[#9C8F85] dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30 focus:border-[#F26D5B] transition-all"
                placeholder="SynxAI Growth"
              />
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full mt-2 py-3 px-4 bg-gradient-to-r from-[#F26D5B] to-[#FF8E53] hover:from-[#E05947] hover:to-[#F26D5B] text-white font-bold text-sm rounded-xl shadow-lg shadow-[#F26D5B]/25 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          data-testid="auth-submit"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Please wait...</span>
            </>
          ) : (
            <>
              <span>{mode === 'login' ? 'Sign In to Workspace' : 'Create Free Account'}</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>
    </div>
  );
}

export default AuthForm;
