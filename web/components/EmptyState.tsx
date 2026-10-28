interface EmptyStateProps {
  message: string;
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="py-4 px-3 text-center border border-dashed border-neutral-200 dark:border-neutral-800 rounded bg-neutral-50/50 dark:bg-neutral-900/30">
      <p className="text-xs font-mono text-neutral-500 dark:text-neutral-400">
        {message}
      </p>
    </div>
  );
}
