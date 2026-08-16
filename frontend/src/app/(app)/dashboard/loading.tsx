/**
 * Shown while the server component waits on /me/summary. Laid out like the real page so
 * the content does not jump when it arrives — the tall block is the headline number and
 * the button under it, which is what people are waiting for.
 */
export default function DashboardLoading() {
  return (
    <div className="animate-pulse">
      <div className="mb-5 h-8 w-56 rounded-control bg-surface" />

      <div className="h-56 rounded-card bg-surface" />

      <div className="mt-8 mb-3 h-6 w-32 rounded-control bg-surface" />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="h-44 rounded-card bg-surface" />
        <div className="h-44 rounded-card bg-surface" />
      </div>
    </div>
  );
}
