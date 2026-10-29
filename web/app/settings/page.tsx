import { Metadata } from "next";
import { supabase } from "@/lib/supabase";
import { SettingsForm, SettingsData, PortfolioCompany } from "@/components/settings/SettingsForm";

export const metadata: Metadata = {
  title: "Settings",
  description: "Alert thresholds, filing category toggles, and portfolio management.",
};

export const revalidate = 60;

export default async function SettingsPage() {
  const [settingsRes, companiesRes] = await Promise.all([
    supabase.from("settings").select("*").eq("id", 1).maybeSingle(),
    supabase
      .from("companies")
      .select("ticker, name, sector")
      .eq("in_portfolio", true)
      .order("ticker"),
  ]);

  const initialSettings: SettingsData = settingsRes.data || {
    id: 1,
    volume_multiple: 2.0,
    volume_lookback_days: 20,
    price_move_pct: 5.0,
    digest_window_hours: 24.0,
    alert_categories: [
      "results",
      "M&A",
      "management_change",
      "fund_raise",
      "litigation",
      "credit_rating",
      "pledging",
    ],
  };

  const portfolioCompanies: PortfolioCompany[] = (companiesRes.data || []) as PortfolioCompany[];

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
            Alert thresholds, monitored filing categories, and portfolio configuration.
          </p>
        </header>

        {/* Settings Form */}
        <SettingsForm
          initialSettings={initialSettings}
          portfolioCompanies={portfolioCompanies}
        />
      </div>
    </main>
  );
}
