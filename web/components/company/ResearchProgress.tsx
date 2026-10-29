"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Company } from "@/lib/types";

export interface ResearchJob {
  ticker: string;
  status: "queued" | "running" | "done" | "failed";
  step?: string | null;
  error?: string | null;
  requested_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
}

interface ResearchProgressProps {
  ticker: string;
  initialJob?: ResearchJob | null;
  company?: Company | null;
}

const CHECKLIST_STEPS = [
  "Finding filings and transcripts",
  "Reading earnings calls",
  "Checking promises against results",
  "Crunching the numbers",
  "Reading the annual report",
  "Writing the bull and bear case",
];

export function ResearchProgress({
  ticker,
  initialJob,
  company,
}: ResearchProgressProps) {
  const router = useRouter();
  const [job, setJob] = useState<ResearchJob | null>(initialJob || null);
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  // Poll research_jobs every 5 seconds
  useEffect(() => {
    let timer: NodeJS.Timeout;

    async function pollJob() {
      try {
        const res = await fetch(`/api/research?ticker=${encodeURIComponent(ticker)}`, {
          cache: "no-store",
        });
        if (!res.ok) return;
        const data = await res.json();
        const currentJob: ResearchJob | null = data.job;

        if (currentJob) {
          setJob(currentJob);
          if (currentJob.status === "done") {
            // Trigger refresh/reload to load compiled research
            router.refresh();
            window.location.reload();
          }
        }
      } catch (err) {
        console.error("Failed to poll research job:", err);
      }
    }

    // Initial check & interval
    pollJob();
    timer = setInterval(pollJob, 5000);

    return () => clearInterval(timer);
  }, [ticker, router]);

  // Live timer for elapsed time
  useEffect(() => {
    const startTimeStr = job?.started_at || job?.requested_at;
    const startMs = startTimeStr ? new Date(startTimeStr).getTime() : Date.now();

    const interval = setInterval(() => {
      const now = Date.now();
      const secs = Math.max(0, Math.floor((now - startMs) / 1000));
      setElapsedSeconds(secs);
    }, 1000);

    return () => clearInterval(interval);
  }, [job?.started_at, job?.requested_at]);

  async function handleRetry() {
    setIsRetrying(true);
    setRetryError(null);
    try {
      const res = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      });
      const data = await res.json();
      if (!res.ok) {
        setRetryError(data.error || "Failed to start research");
      } else {
        setJob({
          ticker,
          status: (data.status as any) || "queued",
          step: CHECKLIST_STEPS[0],
          requested_at: new Date().toISOString(),
        });
      }
    } catch (err: any) {
      setRetryError(err?.message || "Failed to connect");
    } finally {
      setIsRetrying(false);
    }
  }

  const formatElapsed = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const remainingSecs = sec % 60;
    if (mins === 0) return `${remainingSecs}s`;
    return `${mins}m ${remainingSecs < 10 ? `0${remainingSecs}` : remainingSecs}s`;
  };

  const currentStep = job?.step || CHECKLIST_STEPS[0];
  let currentStepIdx = CHECKLIST_STEPS.indexOf(currentStep);
  if (currentStepIdx === -1) {
    // If not exact match, find closest or default to 0
    if (currentStep.toLowerCase().includes("corpus")) currentStepIdx = 0;
    else if (currentStep.toLowerCase().includes("concall") || currentStep.toLowerCase().includes("extract")) currentStepIdx = 1;
    else if (currentStep.toLowerCase().includes("promis") || currentStep.toLowerCase().includes("judge")) currentStepIdx = 2;
    else if (currentStep.toLowerCase().includes("number")) currentStepIdx = 3;
    else if (currentStep.toLowerCase().includes("snapshot") || currentStep.toLowerCase().includes("annual")) currentStepIdx = 4;
    else if (currentStep.toLowerCase().includes("bull")) currentStepIdx = 5;
    else currentStepIdx = 0;
  }

  // If job failed
  if (job?.status === "failed") {
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

        <div className="p-6 rounded border border-rose-200 dark:border-rose-900/40 bg-white dark:bg-neutral-900/80 space-y-4 text-left">
          <div className="space-y-1">
            <div className="flex items-baseline justify-between">
              <span className="text-xl font-mono font-bold text-neutral-950 dark:text-neutral-50">
                {ticker}
              </span>
              <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
                Research Failed
              </span>
            </div>
            {company?.name && (
              <div className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
                {company.name}
              </div>
            )}
          </div>

          <div className="p-3 rounded bg-rose-50/50 dark:bg-rose-950/20 border border-rose-100 dark:border-rose-900/30 text-xs font-sans text-rose-800 dark:text-rose-300">
            {job.error || "An unexpected error occurred while compiling research."}
          </div>

          {retryError && (
            <div className="text-[11px] font-sans text-rose-600 dark:text-rose-400">
              {retryError}
            </div>
          )}

          <div className="pt-2">
            <button
              type="button"
              onClick={handleRetry}
              disabled={isRetrying}
              className="w-full py-2.5 px-4 rounded text-xs font-mono uppercase tracking-wider font-semibold bg-neutral-900 hover:bg-neutral-800 text-white dark:bg-neutral-100 dark:hover:bg-neutral-200 dark:text-neutral-950 transition-colors disabled:opacity-50"
            >
              {isRetrying ? "Starting..." : "Try again"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Job running or queued
  return (
    <div className="space-y-5 py-6 max-w-sm mx-auto">
      {/* Top back navigation */}
      <div className="flex justify-between items-center mb-1">
        <Link
          href="/research"
          className="inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-wider text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100 transition-colors"
        >
          <span>←</span>
          <span>All Research</span>
        </Link>
        <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500 tabular-nums">
          {formatElapsed(elapsedSeconds)} elapsed
        </span>
      </div>

      <div className="p-5 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/80 space-y-5 shadow-sm">
        {/* Header */}
        <div className="border-b border-neutral-100 dark:border-neutral-800/80 pb-3">
          <div className="flex items-baseline justify-between">
            <span className="text-xl font-mono font-bold text-neutral-950 dark:text-neutral-50">
              {ticker}
            </span>
            <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              {job?.status === "queued" ? "Queued" : "Researching"}
            </span>
          </div>
          {company?.name && (
            <div className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mt-0.5">
              {company.name}
            </div>
          )}
        </div>

        {/* Steps Checklist */}
        <div className="space-y-3 py-1">
          {CHECKLIST_STEPS.map((stepName, idx) => {
            const isDone = idx < currentStepIdx;
            const isCurrent = idx === currentStepIdx;
            const isPending = idx > currentStepIdx;

            return (
              <div
                key={stepName}
                className={`flex items-start gap-3 text-xs transition-opacity ${
                  isPending
                    ? "opacity-40 text-neutral-400 dark:text-neutral-600"
                    : isCurrent
                    ? "font-medium text-neutral-950 dark:text-neutral-100"
                    : "text-neutral-600 dark:text-neutral-400"
                }`}
              >
                {/* Step Icon */}
                <div className="mt-0.5 flex-shrink-0">
                  {isDone ? (
                    <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-400 text-[10px] font-mono font-bold">
                      ✓
                    </span>
                  ) : isCurrent ? (
                    <span className="relative flex h-4 w-4 items-center justify-center">
                      <span className="animate-ping absolute inline-flex h-3 w-3 rounded-full bg-amber-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                    </span>
                  ) : (
                    <span className="inline-flex items-center justify-center w-4 h-4 rounded-full border border-neutral-300 dark:border-neutral-700 text-[9px] font-mono text-neutral-400">
                      {idx + 1}
                    </span>
                  )}
                </div>

                {/* Step Label */}
                <div className="flex-1 leading-snug">
                  <span>{stepName}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Reassurance Subtext */}
        <div className="border-t border-neutral-100 dark:border-neutral-800/80 pt-3 text-center">
          <p className="text-[11px] font-sans text-neutral-500 dark:text-neutral-400 leading-relaxed">
            Usually about 4 minutes. You can leave; it’ll be under Research.
          </p>
        </div>
      </div>
    </div>
  );
}
