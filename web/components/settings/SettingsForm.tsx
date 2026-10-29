"use client";

import { useState } from "react";
import { supabase } from "@/lib/supabase";

export interface SettingsData {
  id: number;
  volume_multiple: number;
  volume_lookback_days: number;
  price_move_pct: number;
  digest_window_hours?: number;
  alert_categories: string[];
  updated_at?: string;
}

export interface PortfolioCompany {
  ticker: string;
  name: string;
  sector: string;
}

interface SettingsFormProps {
  initialSettings: SettingsData;
  portfolioCompanies: PortfolioCompany[];
}

interface CategoryOption {
  id: string;
  label: string;
  description: string;
}

const ALL_CATEGORIES: CategoryOption[] = [
  { id: "results", label: "Results", description: "Quarterly and annual financial results and releases" },
  { id: "M&A", label: "M&A", description: "Mergers, acquisitions, joint ventures, and divestments" },
  { id: "management_change", label: "Management change", description: "MD, CEO, CFO, key executive, and auditor appointments or exits" },
  { id: "fund_raise", label: "Fund raise", description: "Equity raises, preferential issues, QIPs, and debt issuances" },
  { id: "litigation", label: "Litigation", description: "Material disputes, tax demands, and regulatory orders" },
  { id: "credit_rating", label: "Credit rating", description: "Upgrades, downgrades, or outlook updates by rating agencies" },
  { id: "pledging", label: "Pledging", description: "Promoter share encumbrance, creation, or revocation" },
  { id: "dividend", label: "Dividend", description: "Dividend declarations, record dates, and changes (off by default)" },
  { id: "capex", label: "CapEx", description: "Plant expansions, commissioning, and major capacity additions (off by default)" },
  { id: "insider_trading", label: "Insider trading", description: "PIT disclosures, promoter buying or selling in open market (off by default)" },
];

export function SettingsForm({ initialSettings, portfolioCompanies }: SettingsFormProps) {
  const [volumeMultiple, setVolumeMultiple] = useState<number>(
    initialSettings.volume_multiple ?? 2.0
  );
  const [volumeDays, setVolumeDays] = useState<number>(
    initialSettings.volume_lookback_days ?? 20
  );
  const [priceMovePct, setPriceMovePct] = useState<number>(
    initialSettings.price_move_pct ?? 5.0
  );
  const [selectedCategories, setSelectedCategories] = useState<string[]>(
    initialSettings.alert_categories || [
      "results",
      "M&A",
      "management_change",
      "fund_raise",
      "litigation",
      "credit_rating",
      "pledging",
    ]
  );

  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function toggleCategory(catId: string) {
    setSaveStatus("idle");
    setSelectedCategories((prev) =>
      prev.includes(catId) ? prev.filter((id) => id !== catId) : [...prev, catId]
    );
  }

  async function handleSave(e?: React.FormEvent) {
    if (e) e.preventDefault();
    setSaving(true);
    setSaveStatus("idle");
    setErrorMessage(null);

    try {
      const { error } = await supabase
        .from("settings")
        .update({
          volume_multiple: volumeMultiple,
          volume_lookback_days: volumeDays,
          price_move_pct: priceMovePct,
          alert_categories: selectedCategories,
          updated_at: new Date().toISOString(),
        })
        .eq("id", 1);

      if (error) {
        throw error;
      }
      setSaveStatus("success");
    } catch (err: any) {
      console.error("Failed to save settings:", err);
      setSaveStatus("error");
      setErrorMessage(err?.message || "Failed to save settings to database.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="space-y-8">
      {/* Alert Thresholds */}
      <section className="space-y-4">
        <h2 className="text-[11px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
          Alert Thresholds
        </h2>

        <div className="rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 divide-y divide-neutral-100 dark:divide-neutral-800/60">
          {/* Volume Spike */}
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-medium text-neutral-900 dark:text-neutral-100">
                Volume spike
              </span>
              <span className="font-mono text-xs font-bold text-neutral-900 dark:text-neutral-50 bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded">
                {volumeMultiple.toFixed(1)}×
              </span>
            </div>
            <p className="text-xs font-sans text-neutral-600 dark:text-neutral-400 leading-normal">
              Alert when volume is above{" "}
              <strong className="text-neutral-950 dark:text-neutral-50 font-mono">
                {volumeMultiple.toFixed(1)}×
              </strong>{" "}
              its{" "}
              <strong className="text-neutral-950 dark:text-neutral-50 font-mono">
                {volumeDays}
              </strong>
              -day average.
            </p>

            <div className="flex items-center gap-3 pt-1">
              <button
                type="button"
                onClick={() => {
                  setSaveStatus("idle");
                  setVolumeMultiple((prev) => Math.max(1.5, Math.round((prev - 0.5) * 10) / 10));
                }}
                disabled={volumeMultiple <= 1.5}
                aria-label="Decrease volume multiple"
                className="w-11 h-11 flex items-center justify-center rounded border border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800/80 text-neutral-700 dark:text-neutral-200 text-sm font-mono font-bold hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors disabled:opacity-40"
              >
                −
              </button>
              <div className="flex-1 px-1">
                <input
                  type="range"
                  min="1.5"
                  max="5.0"
                  step="0.1"
                  value={volumeMultiple}
                  onChange={(e) => {
                    setSaveStatus("idle");
                    setVolumeMultiple(parseFloat(e.target.value));
                  }}
                  className="w-full accent-neutral-900 dark:accent-neutral-100 cursor-pointer h-2 bg-neutral-200 dark:bg-neutral-800 rounded-lg"
                />
              </div>
              <button
                type="button"
                onClick={() => {
                  setSaveStatus("idle");
                  setVolumeMultiple((prev) => Math.min(5.0, Math.round((prev + 0.5) * 10) / 10));
                }}
                disabled={volumeMultiple >= 5.0}
                aria-label="Increase volume multiple"
                className="w-11 h-11 flex items-center justify-center rounded border border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800/80 text-neutral-700 dark:text-neutral-200 text-sm font-mono font-bold hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors disabled:opacity-40"
              >
                +
              </button>
            </div>
          </div>

          {/* Price Move */}
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-medium text-neutral-900 dark:text-neutral-100">
                Price move
              </span>
              <span className="font-mono text-xs font-bold text-neutral-900 dark:text-neutral-50 bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded">
                {priceMovePct}%
              </span>
            </div>
            <p className="text-xs font-sans text-neutral-600 dark:text-neutral-400 leading-normal">
              Alert when a stock moves more than{" "}
              <strong className="text-neutral-950 dark:text-neutral-50 font-mono">
                {priceMovePct}%
              </strong>{" "}
              in a day.
            </p>

            <div className="flex items-center gap-3 pt-1">
              <button
                type="button"
                onClick={() => {
                  setSaveStatus("idle");
                  setPriceMovePct((prev) => Math.max(1, prev - 1));
                }}
                disabled={priceMovePct <= 1}
                aria-label="Decrease price move threshold"
                className="w-11 h-11 flex items-center justify-center rounded border border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800/80 text-neutral-700 dark:text-neutral-200 text-sm font-mono font-bold hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors disabled:opacity-40"
              >
                −
              </button>
              <div className="flex-1 px-1">
                <input
                  type="range"
                  min="1"
                  max="15"
                  step="1"
                  value={priceMovePct}
                  onChange={(e) => {
                    setSaveStatus("idle");
                    setPriceMovePct(parseInt(e.target.value, 10));
                  }}
                  className="w-full accent-neutral-900 dark:accent-neutral-100 cursor-pointer h-2 bg-neutral-200 dark:bg-neutral-800 rounded-lg"
                />
              </div>
              <button
                type="button"
                onClick={() => {
                  setSaveStatus("idle");
                  setPriceMovePct((prev) => Math.min(15, prev + 1));
                }}
                disabled={priceMovePct >= 15}
                aria-label="Increase price move threshold"
                className="w-11 h-11 flex items-center justify-center rounded border border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800/80 text-neutral-700 dark:text-neutral-200 text-sm font-mono font-bold hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors disabled:opacity-40"
              >
                +
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Filing Alerts (Toggles) */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-[11px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            Filing Alerts ({selectedCategories.length} active)
          </h2>
          <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
            Tap to toggle
          </span>
        </div>

        <div className="rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 divide-y divide-neutral-100 dark:divide-neutral-800/60">
          {ALL_CATEGORIES.map((cat) => {
            const isEnabled = selectedCategories.includes(cat.id);
            return (
              <div
                key={cat.id}
                onClick={() => toggleCategory(cat.id)}
                className="p-3.5 flex items-center justify-between cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800/30 transition-colors select-none min-h-[52px]"
                role="checkbox"
                aria-checked={isEnabled}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === " " || e.key === "Enter") {
                    e.preventDefault();
                    toggleCategory(cat.id);
                  }
                }}
              >
                <div className="pr-4 space-y-0.5">
                  <div className="text-xs font-mono font-medium text-neutral-900 dark:text-neutral-100">
                    {cat.label}
                  </div>
                  <div className="text-[11px] font-sans text-neutral-500 dark:text-neutral-400">
                    {cat.description}
                  </div>
                </div>

                {/* Accessible Toggle Switch */}
                <div
                  className={`w-11 h-6 flex items-center rounded-full p-1 duration-200 ease-in-out shrink-0 ${
                    isEnabled
                      ? "bg-neutral-950 dark:bg-neutral-50"
                      : "bg-neutral-200 dark:bg-neutral-700"
                  }`}
                >
                  <div
                    className={`bg-white dark:bg-neutral-950 w-4 h-4 rounded-full shadow-md transform duration-200 ease-in-out ${
                      isEnabled ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Save Button & Feedback Banner */}
      <div className="space-y-3 pt-1">
        {saveStatus === "success" && (
          <div
            role="status"
            className="p-3 rounded border border-emerald-300 dark:border-emerald-800/60 bg-emerald-50 dark:bg-emerald-950/40 text-xs font-sans text-emerald-800 dark:text-emerald-200 leading-relaxed"
          >
            Saved. New alerts use this from the next check (within 30 min).
          </div>
        )}

        {saveStatus === "error" && errorMessage && (
          <div
            role="alert"
            className="p-3 rounded border border-rose-300 dark:border-rose-800/60 bg-rose-50 dark:bg-rose-950/40 text-xs font-sans text-rose-800 dark:text-rose-200 leading-relaxed"
          >
            {errorMessage}
          </div>
        )}

        <button
          type="submit"
          disabled={saving}
          className="w-full min-h-[44px] py-2.5 px-4 rounded text-xs font-mono uppercase tracking-wider font-semibold bg-neutral-950 hover:bg-neutral-800 text-white dark:bg-neutral-50 dark:hover:bg-neutral-200 dark:text-neutral-950 transition-colors disabled:opacity-50"
        >
          {saving ? "Saving settings..." : "Save settings"}
        </button>
      </div>

      {/* Your Portfolio */}
      <section className="space-y-3 pt-4 border-t border-neutral-200 dark:border-neutral-800">
        <div className="flex items-baseline justify-between">
          <h2 className="text-[11px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            Your portfolio ({portfolioCompanies.length})
          </h2>
          <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
            Edit in portfolio.yaml
          </span>
        </div>

        <div className="rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 divide-y divide-neutral-100 dark:divide-neutral-800/60 text-xs font-sans">
          {portfolioCompanies.map((c) => (
            <div
              key={c.ticker}
              className="p-3 flex items-center justify-between hover:bg-neutral-50/50 dark:hover:bg-neutral-800/20"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span className="font-mono font-bold text-neutral-950 dark:text-neutral-50 text-xs">
                  {c.ticker}
                </span>
                <span className="text-neutral-700 dark:text-neutral-300 truncate">
                  {c.name}
                </span>
              </div>
              <span className="text-[11px] font-mono text-neutral-400 dark:text-neutral-500 shrink-0 ml-2">
                {c.sector}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* How FINN Works */}
      <section className="space-y-3 pt-4 border-t border-neutral-200 dark:border-neutral-800">
        <h2 className="text-[11px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
          How FINN works
        </h2>
        <div className="rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 p-4 text-xs font-sans text-neutral-600 dark:text-neutral-400 space-y-3 leading-relaxed">
          <div className="flex gap-2.5 items-start">
            <span className="font-mono font-bold text-neutral-900 dark:text-neutral-200">1.</span>
            <p>
              <strong className="text-neutral-900 dark:text-neutral-200">Primary sources only:</strong>{" "}
              FINN builds its brief and guidance tracking exclusively from earnings-call transcripts, investor presentations, annual reports, exchange filings, and reported financials. No news or broker research.
            </p>
          </div>
          <div className="flex gap-2.5 items-start">
            <span className="font-mono font-bold text-neutral-900 dark:text-neutral-200">2.</span>
            <p>
              <strong className="text-neutral-900 dark:text-neutral-200">Cheap model for reading:</strong>{" "}
              Fast bulk models (Gemini Flash-Lite) read filings, classify announcements, and extract guidance quotes verbatim.
            </p>
          </div>
          <div className="flex gap-2.5 items-start">
            <span className="font-mono font-bold text-neutral-900 dark:text-neutral-200">3.</span>
            <p>
              <strong className="text-neutral-900 dark:text-neutral-200">Strong model for judging:</strong>{" "}
              Deep reasoning models (Gemini Flash) verify evidence timelines, cross-check numerical targets against audited numbers, and issue strict guidance verdicts.
            </p>
          </div>
          <div className="flex gap-2.5 items-start">
            <span className="font-mono font-bold text-neutral-900 dark:text-neutral-200">4.</span>
            <p>
              <strong className="text-neutral-900 dark:text-neutral-200">Everything cached:</strong>{" "}
              All LLM queries and intermediate artifacts are deterministically cached by hash, ensuring reproducibility and immediate page loads.
            </p>
          </div>
        </div>
      </section>
    </form>
  );
}

