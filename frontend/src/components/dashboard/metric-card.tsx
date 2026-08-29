/**
 * One number on the dashboard, with the period it covers and — where the data is
 * partial — how much of it the number is actually made of.
 *
 * `period` is not decoration. The activity totals are lifetime and the campaign card
 * beside them is a window, so a screen with both and no labels invites a member to read
 * one as the other. Every card here says which it is.
 *
 * `note` is where "รวมจาก 18 ใน 24 ครั้ง" goes. A calorie total over the eighteen runs
 * that happened to carry a figure reads as the total for all twenty-four unless the
 * screen says otherwise, which is golden rule #4 applied to a subtotal.
 */
const ACCENTS = {
  brand: "bg-brand-tint text-brand",
  blue: "bg-accent-blue-tint text-accent-blue",
  violet: "bg-accent-violet-tint text-accent-violet",
  amber: "bg-accent-amber-tint text-accent-amber",
  rose: "bg-accent-rose-tint text-accent-rose",
} as const;

export function MetricCard({
  label,
  period,
  accent = "brand",
  icon,
  children,
  note,
}: {
  label: string;
  period: string;
  accent?: keyof typeof ACCENTS;
  icon: React.ReactNode;
  /** The value, so a card can render "6 ชม. 12 น." or an empty state in its place. */
  children: React.ReactNode;
  note?: React.ReactNode;
}) {
  return (
    <section className="card flex flex-col">
      <div className="flex items-start justify-between gap-2">
        <span className="inline-flex items-center rounded-full border border-border bg-background px-2.5 py-1 text-xs font-semibold text-muted">
          {period}
        </span>
        <span
          aria-hidden
          className={`grid size-10 shrink-0 place-items-center rounded-control ${ACCENTS[accent]}`}
        >
          {icon}
        </span>
      </div>
      <p className="mt-3 font-semibold">{label}</p>
      <div className="mt-1">{children}</div>
      {note ? <p className="mt-2 text-xs text-muted">{note}</p> : null}
    </section>
  );
}

/** The value line inside a MetricCard: a big tabular number and a small unit. */
export function MetricValue({
  value,
  unit,
}: {
  value: React.ReactNode;
  unit?: string;
}) {
  return (
    <p className="text-3xl font-bold tabular-nums">
      {value}
      {unit ? <span className="ml-1.5 text-base font-semibold text-muted">{unit}</span> : null}
    </p>
  );
}

/** What a card shows instead of a number nobody has recorded. Never a zero: "0 kcal"
 * is a claim that the member burned none, which is not what an absent figure means. */
export function MetricEmpty({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-base text-muted">{children}</p>;
}
