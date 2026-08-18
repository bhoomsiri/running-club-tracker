"use client";

import { useEffect } from "react";

/**
 * A panel over the page: a sheet from the bottom on a phone, a centred box on a laptop.
 *
 * Used where a form field needs more room than the field has — picking from a list of
 * thirty units, reading a size chart. Escape closes it, tapping the backdrop closes it,
 * and the page behind stops scrolling while it is open so a thumb aiming at the list
 * cannot drag the page instead.
 *
 * `ZoomableImage` keeps its own lightbox rather than using this: a photo wants the whole
 * screen and no chrome, which is a different thing from a titled panel.
 */
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
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
      aria-label={title}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 sm:items-center sm:p-4"
    >
      <div
        // The backdrop closes; the panel must not, or every tap inside dismisses it.
        onClick={(event) => event.stopPropagation()}
        className="flex max-h-[85vh] w-full flex-col rounded-t-card border border-border bg-background sm:max-w-md sm:rounded-card"
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="btn btn-secondary shrink-0">
            ปิด
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
          {children}
        </div>
      </div>
    </div>
  );
}
