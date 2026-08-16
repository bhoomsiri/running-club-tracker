export default function LeaderboardLoading() {
  return (
    <div className="animate-pulse">
      <div className="mb-6 h-8 w-44 rounded-lg bg-surface" />
      <div className="mb-5 h-28 rounded-xl bg-surface" />
      <div className="space-y-2">
        {Array.from({ length: 8 }, (_, index) => (
          <div key={index} className="h-16 rounded-xl bg-surface" />
        ))}
      </div>
    </div>
  );
}
