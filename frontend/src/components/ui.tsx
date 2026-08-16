import Link from "next/link";

/**
 * The presentational primitives every screen is built from.
 *
 * Hand-written rather than pulled from a component library: a card, a badge and a bar
 * are a few lines of Tailwind between them, and a library would bring a CLI, a config
 * file and a handful of runtime dependencies to replace them.
 *
 * The sizing rules live in globals.css as `btn`, `card`, `tap` and `input-field`, so a
 * screen that needs a button outside these components still gets 48px and the right
 * radius by using the same class. These wrap that, they do not redefine it.
 */

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <section className={`card ${className}`}>{children}</section>;
}

/**
 * The one thing a screen is for.
 *
 * Full width on a phone by default: a thumb reaching across a 390px screen should not
 * have to aim. `tone="secondary"` is for everything that must be available without
 * competing with it.
 */
export function Button({
  children,
  onClick,
  type = "button",
  tone = "primary",
  disabled = false,
  fullWidth = true,
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  tone?: "primary" | "secondary";
  disabled?: boolean;
  fullWidth?: boolean;
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`btn ${tone === "primary" ? "btn-primary" : "btn-secondary"} ${
        fullWidth ? "w-full" : ""
      } ${className}`}
    >
      {children}
    </button>
  );
}

/** A link that looks and measures like a button. */
export function ButtonLink({
  href,
  children,
  tone = "primary",
  fullWidth = true,
  className = "",
}: {
  href: string;
  children: React.ReactNode;
  tone?: "primary" | "secondary";
  fullWidth?: boolean;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={`btn ${tone === "primary" ? "btn-primary" : "btn-secondary"} ${
        fullWidth ? "w-full" : ""
      } ${className}`}
    >
      {children}
    </Link>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "brand" | "success" | "warning" | "danger";
}) {
  // Every pair below clears 4.5:1 against its own background. The success tone used
  // emerald-600, which is 3.4:1 on white — it reads as green and not as text.
  const tones = {
    neutral: "bg-border text-foreground",
    brand: "bg-brand-tint text-brand",
    success: "bg-emerald-600/15 text-emerald-800 dark:text-emerald-300",
    warning: "bg-amber-500/20 text-amber-800 dark:text-amber-200",
    danger: "bg-red-600/15 text-red-800 dark:text-red-300",
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}
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
      className="h-3 w-full overflow-hidden rounded-full bg-border"
    >
      <div
        className="h-full rounded-full bg-brand transition-[width] duration-500"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}

/**
 * Nothing here yet — and, always, what to do about it.
 *
 * An empty state that only says "ไม่มีข้อมูล" leaves a member stuck on a screen with no
 * way forward, so `action` is part of the shape rather than something to remember.
 */
export function EmptyState({
  children,
  action,
}: {
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-card border border-dashed border-border px-4 py-8 text-center">
      <p className="text-base text-muted">{children}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

/** The heading above a group of cards. One weight, one size, everywhere. */
export function SectionHeading({
  children,
  action,
}: {
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="mt-8 mb-3 flex items-baseline justify-between gap-3">
      <h2 className="text-lg font-semibold">{children}</h2>
      {action}
    </div>
  );
}
