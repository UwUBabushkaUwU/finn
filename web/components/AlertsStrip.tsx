import { Alert, Price } from "@/lib/types";

interface AlertsStripProps {
  alerts: Alert[];
  pricesMap: Record<string, Price>;
}

export function AlertsStrip({ alerts, pricesMap }: AlertsStripProps) {
  // Filter only volume_spike and price_move alerts
  const relevantAlerts = alerts.filter(
    (a) => a.kind === "volume_spike" || a.kind === "price_move"
  );

  if (relevantAlerts.length === 0) {
    return null;
  }

  return (
    <section
      aria-label="Today's price and volume alerts"
      className="py-2 border-y border-neutral-200 dark:border-neutral-800"
    >
      <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5 text-xs font-mono tabular-nums">
        <span className="text-[10px] uppercase font-bold tracking-wider text-neutral-400 dark:text-neutral-500 whitespace-nowrap pl-0.5">
          Alerts:
        </span>
        <div className="flex items-center gap-1.5 flex-nowrap">
          {relevantAlerts.map((alert) => {
            const price = pricesMap[alert.ticker];
            const pctChange = price?.pct_change ?? (alert.kind === "price_move" ? alert.value ?? 0 : 0);
            const isUp = pctChange >= 0;
            const arrow = isUp ? "▲" : "▼";
            const sign = pctChange >= 0 ? "+" : "−";
            const pctStr = `${sign}${Math.abs(pctChange).toFixed(1)}%`;

            let displayText = "";
            if (alert.kind === "volume_spike") {
              const multiple = alert.value != null ? alert.value.toFixed(1) : "2.0";
              displayText = `${alert.ticker} vol ${multiple}× · ${pctStr}`;
            } else if (alert.kind === "price_move") {
              displayText = `${alert.ticker} ${pctStr}`;
            }

            return (
              <span
                key={alert.id}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border whitespace-nowrap text-[11px] font-medium transition-colors ${
                  isUp
                    ? "text-emerald-700 bg-emerald-50/70 border-emerald-200 dark:text-emerald-400 dark:bg-emerald-950/30 dark:border-emerald-900/60"
                    : "text-red-700 bg-red-50/70 border-red-200 dark:text-red-400 dark:bg-red-950/30 dark:border-red-900/60"
                }`}
              >
                <span className="text-[9px]">{arrow}</span>
                <span>{displayText}</span>
              </span>
            );
          })}
        </div>
      </div>
    </section>
  );
}
