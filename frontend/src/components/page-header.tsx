/**
 * The top of a screen: what this page is, and one line on what to do with it.
 *
 * The subtitle is 16px rather than the 14px it started at — on the screens that have one
 * it is doing real work ("ระบบนับให้ทันที ไม่ต้องรออนุมัติ"), and instructions set in
 * small grey type are instructions people skip.
 */
export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
      {subtitle ? <p className="mt-2 text-base text-muted">{subtitle}</p> : null}
    </header>
  );
}

/** Marks a screen that is scaffolded but not built yet, so it can't be mistaken for one
 * that is finished and broken. */
export function ComingSoon({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-dashed border-border bg-surface p-6 text-base text-muted">
      {children}
    </div>
  );
}
