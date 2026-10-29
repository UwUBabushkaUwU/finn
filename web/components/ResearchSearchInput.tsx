"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const VALID_TICKER_REGEX = /^[A-Z0-9&-]{1,20}$/;

export function ResearchSearchInput() {
  const router = useRouter();
  const [ticker, setTicker] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    // Uppercase and strip invalid characters
    const clean = e.target.value.toUpperCase().replace(/[^A-Z0-9&-]/g, "").slice(0, 20);
    setTicker(clean);
    if (error) setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const cleanTicker = ticker.trim().toUpperCase();

    if (!cleanTicker) {
      setError("Please enter a ticker symbol");
      return;
    }

    if (!VALID_TICKER_REGEX.test(cleanTicker)) {
      setError("Use 1–20 characters: letters, numbers, & or -");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      // Trigger research dispatch or check if ready
      const res = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: cleanTicker }),
      });
      const data = await res.json();

      if (!res.ok && res.status !== 429 && res.status !== 503) {
        // If not a known server setup message, still allow user to navigate to /c/ticker
        console.warn("API response:", data);
      }
      
      // Navigate to /c/[ticker]
      router.push(`/c/${cleanTicker}`);
    } catch (err: any) {
      // On network error, navigate anyway so /c/[ticker] displays state
      router.push(`/c/${cleanTicker}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="relative flex items-center">
        <input
          type="text"
          value={ticker}
          onChange={handleChange}
          placeholder="Research any NSE company: type a ticker"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck="false"
          maxLength={20}
          className="w-full rounded border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3.5 py-2.5 text-sm font-mono uppercase tracking-wide placeholder:font-sans placeholder:normal-case placeholder:tracking-normal placeholder:text-neutral-400 dark:placeholder:text-neutral-500 text-neutral-950 dark:text-neutral-50 focus:border-neutral-950 dark:focus:border-neutral-200 focus:outline-none transition-colors pr-24"
        />
        <button
          type="submit"
          disabled={!ticker || isSubmitting}
          className="absolute right-1.5 top-1.5 bottom-1.5 px-3 rounded bg-neutral-900 hover:bg-neutral-800 text-white dark:bg-neutral-100 dark:hover:bg-neutral-200 dark:text-neutral-950 text-xs font-mono font-medium uppercase tracking-wider transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isSubmitting ? "..." : "Go ↵"}
        </button>
      </div>

      {error && (
        <div className="text-[11px] font-sans text-rose-600 dark:text-rose-400 pl-1">
          {error}
        </div>
      )}
    </form>
  );
}
