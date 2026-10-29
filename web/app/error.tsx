"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global app error:", error);
  }, [error]);

  return (
    <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800">
      <div className="mx-auto max-w-xl px-4 py-16 sm:px-6 text-center space-y-6">
        <div className="p-8 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/70 space-y-4 max-w-md mx-auto">
          <div className="w-12 h-12 rounded-full border border-neutral-300 dark:border-neutral-700 bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center mx-auto text-neutral-600 dark:text-neutral-400">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
          </div>

          <div className="space-y-1.5">
            <h1 className="font-serif text-xl font-normal text-neutral-950 dark:text-neutral-50">
              Database connection issue
            </h1>
            <p className="text-xs font-sans text-neutral-600 dark:text-neutral-400 leading-relaxed">
              Supabase is temporarily unreachable or taking longer than usual to respond. Your saved alerts and cached records are safe.
            </p>
          </div>

          <div className="pt-2 space-y-2">
            <button
              type="button"
              onClick={() => reset()}
              className="w-full min-h-[44px] py-2.5 px-4 rounded text-xs font-mono uppercase tracking-wider font-semibold bg-neutral-950 hover:bg-neutral-800 text-white dark:bg-neutral-50 dark:hover:bg-neutral-200 dark:text-neutral-950 transition-colors"
            >
              Try again
            </button>
            <Link
              href="/"
              className="inline-block w-full min-h-[44px] py-2.5 px-4 rounded text-xs font-mono uppercase tracking-wider text-neutral-600 hover:text-neutral-950 dark:text-neutral-400 dark:hover:text-neutral-100 transition-colors"
            >
              Return to Brief
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}

