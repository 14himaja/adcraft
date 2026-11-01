'use client';

import React from 'react';
import Link from 'next/link';
import { AuthForm } from '../../components/AuthForm';

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#090D16] text-[#F8FAFC] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-6">
        <h2 className="text-3xl font-extrabold text-white tracking-tight">
          AdCraft Studio
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          Sign in to manage your Meta & Instagram ad campaigns
        </p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md flex justify-center">
        <AuthForm initialMode="login" />
      </div>

      <p className="mt-6 text-center text-xs sm:text-sm text-slate-400">
        Need an account?{' '}
        <Link href="/register" className="font-semibold text-[#F26D5B] hover:text-[#FF8E53] transition-colors">
          Register here
        </Link>
      </p>
    </div>
  );
}
