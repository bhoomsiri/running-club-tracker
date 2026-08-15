export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {subtitle ? <p className="mt-1 text-sm text-muted">{subtitle}</p> : null}
    </header>
  );
}

/** Marks a screen that is scaffolded but not built yet, so it can't be mistaken for one
 * that is finished and broken. */
export function ComingSoon({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-surface p-6 text-sm text-muted">
      {children}
    </div>
  );
}
