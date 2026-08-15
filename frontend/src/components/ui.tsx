/**
 * The three presentational primitives the dashboard needs.
 *
 * Hand-written rather than pulled from a component library: a card, a badge and a bar
 * are a dozen lines of Tailwind between them, and a library would bring a CLI, a config
 * file and a handful of runtime dependencies to replace them. Worth revisiting when
 * there are dialogs and forms to build — those are the parts that are genuinely fiddly.
 */

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-border bg-surface p-4 ${className}`}>
      {children}
    </section>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "brand" | "success";
}) {
  const tones = {
    neutral: "bg-border text-foreground",
    brand: "bg-brand/15 text-brand",
    success: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function ProgressBar({ percent, label }: { percent: number; label: string }) {
  return (
    <div
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className="h-2.5 w-full overflow-hidden rounded-full bg-border"
    >
      <div
        className="h-full rounded-full bg-brand transition-[width] duration-500"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
      {children}
    </p>
  );
}
