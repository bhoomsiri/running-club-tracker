export default function RunsLoading() {
  return (
    <div className="animate-pulse">
      <div className="mb-6 h-8 w-40 rounded-lg bg-surface" />
      <div className="mb-4 h-4 w-56 rounded bg-surface" />
      <div className="space-y-3">
        <div className="h-28 rounded-xl bg-surface" />
        <div className="h-28 rounded-xl bg-surface" />
        <div className="h-28 rounded-xl bg-surface" />
      </div>
    </div>
  );
}
