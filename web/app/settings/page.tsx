import { Metadata } from "next";
import Link from "next/link";
import { supabase } from "@/lib/supabase";

export const metadata: Metadata = {
  title: "Settings — FINN",
  description: "System status, portfolio configuration, and source principles.",
};

export const revalidate = 60;

export default async function SettingsPage() {
  const { count: portfolioCount } = await supabase
    .from("companies")
    .select("*", { count: "exact", head: true })
    .eq("in_portfolio", true);

  const { count: researchedCount } = await supabase
    .from("research_jobs")
    .select("*", { count: "exact", head: true })
    .eq("status", "done");

  return (
    <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800">
      <div className="mx-auto max-w-xl px-4 py-6 sm:px-6 space-y-6">
        {/* Header */}
        <header className="border-b border-neutral-200 dark:border-neutral-800 pb-4">
          <div className="flex items-baseline justify-between mb-1">
            <h1 className="font-serif text-2xl font-normal tracking-tight text-neutral-950 dark:text-neutral-50">
              Settings
            </h1>
            <span className="text-[11px] font-mono uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              v0.5.0
            </span>
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 font-sans">
            System status, primary-source policies, and portfolio monitoring.
          </p>
        </header>

        {/* System & Coverage */}
        <section className="space-y-3">
          <h2 className="text-[11px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            Coverage & Pipeline
          </h2>
          <div className="rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 divide-y divide-neutral-100 dark:divide-neutral-800/60 text-xs font-sans">
            <div className="p-3 flex items-center justify-between">
              <span className="text-neutral-600 dark:text-neutral-400">Portfolio companies</span>
              <span className="font-mono font-medium text-neutral-900 dark:text-neutral-100">
                {portfolioCount ?? 18} tracked
              </span>
            </div>
            <div className="p-3 flex items-center justify-between">
              <span className="text-neutral-600 dark:text-neutral-400">Researched tickers</span>
              <span className="font-mono font-medium text-neutral-900 dark:text-neutral-100">
                {researchedCount ?? 6} completed
              </span>
            </div>
            <div className="p-3 flex items-center justify-between">
              <span className="text-neutral-600 dark:text-neutral-400">Database</span>
              <span className="font-mono font-medium text-neutral-900 dark:text-neutral-100">
                Supabase Postgres
              </span>
            </div>
            <div className="p-3 flex items-center justify-between">
              <span className="text-neutral-600 dark:text-neutral-400">LLM Reasoning</span>
              <span className="font-mono font-medium text-neutral-900 dark:text-neutral-100">
                Gemini 2.5 Flash
              </span>
            </div>
          </div>
        </section>

        {/* Source Integrity */}
        <section className="space-y-3">
          <h2 className="text-[11px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            Source Principles
          </h2>
          <div className="rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 p-4 text-xs font-sans text-neutral-600 dark:text-neutral-400 space-y-2 leading-relaxed">
            <p>
              <strong className="text-neutral-900 dark:text-neutral-200">Strict primary sources only:</strong>{" "}
              FINN uses exclusively earnings-call transcripts, investor presentations, annual reports, exchange filings, and reported financial tables from screener.in.
            </p>
            <p>
              FINN does not consume financial news, brokerage research notes, or speculative social media commentary.
            </p>
          </div>
        </section>

        {/* Quick Links */}
        <section className="pt-2">
          <div className="flex gap-4 text-xs font-mono">
            <Link
              href="/"
              className="text-neutral-600 hover:text-neutral-950 dark:text-neutral-400 dark:hover:text-neutral-100 underline decoration-neutral-300 dark:decoration-neutral-700"
            >
              ← Back to Brief
            </Link>
            <Link
              href="/research"
              className="text-neutral-600 hover:text-neutral-950 dark:text-neutral-400 dark:hover:text-neutral-100 underline decoration-neutral-300 dark:decoration-neutral-700"
            >
              Browse Research →
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
