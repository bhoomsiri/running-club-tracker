"use client";

import { useEffect, useState } from "react";

/**
 * A thumbnail that opens full screen when tapped.
 *
 * Used for both kinds of picture in the app — a member's evidence photo and a reward's
 * catalogue photo — because on a phone a 80px square is not enough to check either one.
 *
 * Plain `<img>`, deliberately: every URL here is presigned, lives on a host that changes
 * with the environment, and expires in minutes. There is nothing for an image optimiser
 * to cache, and asking it to fetch the object server-side would put a short-lived
 * capability somewhere it was never meant to go.
 */
export function ZoomableImage({
  src,
  alt,
  className,
}: {
  src: string;
  alt: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`ดูรูปขนาดใหญ่: ${alt}`}
        className="shrink-0"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} className={`bg-border object-cover ${className ?? ""}`} />
      </button>

      {open ? <Lightbox src={src} alt={alt} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function Lightbox({
  src,
  alt,
  onClose,
}: {
  src: string;
  alt: string;
  onClose: () => void;
}) {
  // Escape closes it, and the page behind stops scrolling while it is open.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={alt}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} className="max-h-full max-w-full rounded-lg object-contain" />
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 rounded-full bg-white/90 px-4 py-2 text-sm font-medium text-black"
      >
        ปิด
      </button>
    </div>
  );
}
