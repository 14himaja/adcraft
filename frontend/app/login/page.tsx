'use client';

import React, { Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AuthForm } from '../../components/AuthForm';

function LoginContent() {
  const searchParams = useSearchParams();
  const redirectParam = searchParams.get('redirect') || searchParams.get('return_to');
  const registerHref = redirectParam
    ? `/register?redirect=${encodeURIComponent(redirectParam)}`
    : '/register';

  return (
    <div className="min-h-screen bg-[#090D16] text-[#F8FAFC] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-6">
        <h2 className="text-3xl font-extrabold text-white tracking-tight">
          AdCraft Studio
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          Sign in to connect and manage your social media & advertising channels
        </p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md flex justify-center">
        <AuthForm initialMode="login" />
      </div>

      <p className="mt-6 text-center text-xs sm:text-sm text-slate-400">
        Need an account?{' '}
        <Link href={registerHref} className="font-semibold text-[#F26D5B] hover:text-[#FF8E53] transition-colors">
          Register here
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#090D16] text-[#F8FAFC] flex items-center justify-center text-sm text-slate-400">
          Loading sign-in...
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
