/**
 * Shown while the server component waits on /me/summary. Laid out like the real page so
 * the content does not jump when it arrives.
 */
export default function DashboardLoading() {
  return (
    <div className="animate-pulse">
      <div className="mb-6">
        <div className="h-8 w-48 rounded-lg bg-surface" />
        <div className="mt-2 h-4 w-32 rounded bg-surface" />
      </div>

      <div className="mb-6 h-24 rounded-xl bg-surface" />

      <div className="mb-3 h-4 w-20 rounded bg-surface" />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="h-40 rounded-xl bg-surface" />
        <div className="h-40 rounded-xl bg-surface" />
      </div>
    </div>
  );
}
