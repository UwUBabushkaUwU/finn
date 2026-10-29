"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Company } from "@/lib/types";

interface NoResearchStateProps {
  ticker: string;
  company?: Company | null;
}

export function NoResearchState({ ticker, company }: NoResearchStateProps) {
  const router = useRouter();
  const companyName = company?.name;
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleStartResearch() {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMsg(data.error || "Failed to dispatch research");
      } else {
        // Dispatched or ready, refresh to progress or completed view
        router.refresh();
        window.location.reload();
      }
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to trigger research");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4 py-8 text-center max-w-sm mx-auto">
      <div className="flex justify-start mb-4">
        <Link
          href="/research"
          className="inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-wider text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100 transition-colors"
        >
          <span>←</span>
          <span>All Research</span>
        </Link>
      </div>

      <div className="p-6 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/80 space-y-4">
        <div className="space-y-1">
          <div className="text-xl font-mono font-bold text-neutral-950 dark:text-neutral-50">
            {ticker}
          </div>
          {companyName && (
            <div className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
              {companyName}
            </div>
          )}
          {company?.sector && (
            <div className="text-xs font-mono text-neutral-400 dark:text-neutral-500">
              {company.sector}
            </div>
          )}
        </div>

        <p className="text-xs text-neutral-500 dark:text-neutral-400 leading-relaxed font-sans">
          Primary research has not been compiled for this company yet. Concall transcripts, annual reports, and guidance evaluations are pending.
        </p>

        {errorMsg && (
          <div className="p-2.5 rounded bg-rose-50 dark:bg-rose-950/40 text-[11px] font-sans text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-900/50 text-left">
            {errorMsg}
          </div>
        )}

        <div className="pt-2">
          <button
            type="button"
            onClick={handleStartResearch}
            disabled={loading}
            className="w-full py-2.5 px-4 rounded text-xs font-mono uppercase tracking-wider font-semibold bg-neutral-950 hover:bg-neutral-800 text-white dark:bg-neutral-50 dark:hover:bg-neutral-200 dark:text-neutral-950 transition-colors disabled:opacity-50"
          >
            {loading ? "Starting research..." : "Research this company"}
          </button>
        </div>
      </div>
    </div>
  );
}
