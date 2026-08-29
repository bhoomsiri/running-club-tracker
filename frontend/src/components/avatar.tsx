/**
 * A member's picture, or their initials.
 *
 * The picture comes from Clerk, synced onto the member record by the verified webhook.
 * The backend already sends `null` for anyone who never set one — Clerk gives every
 * account an `image_url` and points it at a generated default, and showing that would be
 * a stranger's styling on a member who chose nothing. So `image_url` here is always a
 * picture somebody picked, and null always means "draw the initials".
 *
 * A plain `<img>`, not `next/image`. These are 40–72px avatars that Clerk already serves
 * resized and cached; routing them through the optimizer would spend Vercel's image
 * budget to make them no smaller, and would need `img.clerk.com` allow-listed in the
 * config to render at all. `referrerPolicy` keeps the app's URLs out of Clerk's logs.
 */
const TONES = [
  "bg-brand text-on-brand",
  "bg-accent-blue text-white",
  "bg-accent-violet text-white",
  "bg-accent-rose text-white",
  "bg-accent-amber text-white",
];

const SIZES = {
  sm: "size-10 text-sm rounded-full",
  md: "size-12 text-base rounded-full",
  lg: "size-18 text-2xl rounded-card",
} as const;

export function Avatar({
  name,
  imageUrl,
  size = "sm",
  seed,
}: {
  name: string;
  imageUrl: string | null;
  size?: keyof typeof SIZES;
  /** Keeps one member the same colour everywhere. Their id, normally. */
  seed?: string;
}) {
  const shape = `${SIZES[size]} shrink-0 overflow-hidden object-cover`;

  if (imageUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- see the note above
      <img
        src={imageUrl}
        alt=""
        aria-hidden
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        className={shape}
      />
    );
  }

  return (
    <span
      aria-hidden
      className={`grid place-items-center font-bold ${shape} ${TONES[toneFor(seed ?? name)]}`}
    >
      {initials(name)}
    </span>
  );
}

/** Two characters. Thai has no case and many members have one long given name, so this
 * takes the first character of each of the first two words and falls back to the first
 * two characters of a single word. */
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return [...words[0]].slice(0, 2).join("");
  return [...words[0]][0] + [...words[1]][0];
}

function toneFor(seed: string): number {
  let sum = 0;
  for (const character of seed) sum = (sum + character.codePointAt(0)!) % 997;
  return sum % TONES.length;
}
