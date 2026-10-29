"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

const WINDOWS: { key: "24h" | "3d" | "7d" | "30d"; label: string }[] = [
  { key: "24h", label: "24h" },
  { key: "3d", label: "3d" },
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
];

export function TimeChips() {
  const searchParams = useSearchParams();
  const currentWindow = searchParams.get("w") || "24h";

  return (
    <nav aria-label="Time window filter" className="flex items-center gap-2 py-1">
      <span className="text-[11px] font-mono uppercase tracking-wider text-neutral-400 dark:text-neutral-500 shrink-0">
        Window:
      </span>
      <div className="flex gap-1.5 flex-wrap">
        {WINDOWS.map(({ key, label }) => {
          const isActive = currentWindow === key;
          const href = key === "24h" ? "/" : `/?w=${key}`;

          return (
            <Link
              key={key}
              href={href}
              scroll={false}
              className={`min-h-[44px] min-w-[44px] px-3 py-2 text-xs font-mono tabular-nums rounded border transition-colors inline-flex items-center justify-center ${
                isActive
                  ? "bg-neutral-900 text-neutral-50 border-neutral-900 dark:bg-neutral-100 dark:text-neutral-950 dark:border-neutral-100 font-semibold"
                  : "bg-neutral-50 text-neutral-600 border-neutral-200 hover:bg-neutral-100 hover:text-neutral-900 dark:bg-neutral-900 dark:text-neutral-400 dark:border-neutral-800 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
