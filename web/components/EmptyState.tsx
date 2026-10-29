import Link from "next/link";

interface EmptyStateProps {
  message: string;
  suggest7d?: boolean;
}

export function EmptyState({ message, suggest7d }: EmptyStateProps) {
  return (
    <div className="py-4 px-3 text-center border border-dashed border-neutral-200 dark:border-neutral-800 rounded bg-neutral-50/50 dark:bg-neutral-900/30 space-y-1.5">
      <p className="text-xs font-mono text-neutral-500 dark:text-neutral-400">
        {message}
      </p>
      {suggest7d && (
        <p className="text-xs font-sans text-neutral-600 dark:text-neutral-400">
          Switch to{" "}
          <Link
            href="/?w=7d"
            className="font-medium text-neutral-900 dark:text-neutral-100 underline decoration-neutral-300 dark:decoration-neutral-700 hover:decoration-neutral-900 dark:hover:decoration-neutral-100"
          >
            7 days
          </Link>{" "}
          to review the week&apos;s filings.
        </p>
      )}
    </div>
  );
}
