"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function TabBar() {
  const pathname = usePathname();

  const isBriefActive = pathname === "/";
  const isResearchActive = pathname === "/research" || pathname.startsWith("/c/");
  const isSettingsActive = pathname === "/settings";

  return (
    <nav
      aria-label="Bottom Navigation"
      className="fixed bottom-0 inset-x-0 z-50 bg-[#fcfbf9]/95 dark:bg-[#0c0d0e]/95 backdrop-blur border-t border-neutral-200 dark:border-neutral-800 pb-[env(safe-area-inset-bottom)]"
    >
      <div className="mx-auto max-w-xl px-6 h-14 flex items-center justify-around">
        {/* Brief */}
        <Link
          href="/"
          className={`flex flex-col items-center justify-center flex-1 py-1 transition-colors ${
            isBriefActive
              ? "text-neutral-950 dark:text-neutral-50 font-semibold"
              : "text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-300"
          }`}
        >
          <svg
            className="w-5 h-5 mb-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={isBriefActive ? 2.2 : 1.7}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
            />
          </svg>
          <span className="text-[10px] font-mono uppercase tracking-wider">
            Brief
          </span>
        </Link>

        {/* Research */}
        <Link
          href="/research"
          className={`flex flex-col items-center justify-center flex-1 py-1 transition-colors ${
            isResearchActive
              ? "text-neutral-950 dark:text-neutral-50 font-semibold"
              : "text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-300"
          }`}
        >
          <svg
            className="w-5 h-5 mb-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={isResearchActive ? 2.2 : 1.7}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
            />
          </svg>
          <span className="text-[10px] font-mono uppercase tracking-wider">
            Research
          </span>
        </Link>

        {/* Settings */}
        <Link
          href="/settings"
          className={`flex flex-col items-center justify-center flex-1 py-1 transition-colors ${
            isSettingsActive
              ? "text-neutral-950 dark:text-neutral-50 font-semibold"
              : "text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-300"
          }`}
        >
          <svg
            className="w-5 h-5 mb-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={isSettingsActive ? 2.2 : 1.7}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
          </svg>
          <span className="text-[10px] font-mono uppercase tracking-wider">
            Settings
          </span>
        </Link>
      </div>
    </nav>
  );
}
