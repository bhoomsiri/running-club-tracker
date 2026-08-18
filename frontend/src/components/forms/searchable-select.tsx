"use client";

import { useEffect, useRef, useState } from "react";

import { Modal } from "@/components/modal";

/**
 * Pick one of a long list — or type your own.
 *
 * Thirty units and thirty-four job titles are too many for a native `<select>` on a
 * phone: the wheel picker gives no way to search, so finding "งานศัลยกรรมกระดูกและข้อ"
 * means spinning past twenty-five others. Tapping the field opens a sheet with a search
 * box at the top, and typing two or three characters narrows it to a handful.
 *
 * The last option is always "อื่นๆ (ระบุเอง)". What the member types there is saved to
 * the field exactly as typed — and is **not** added to the list: the list is a constant
 * in lib/roster-options.ts and only a code change grows it. That keeps the picker honest
 * about being the hospital's org chart rather than a collection of everyone's typos.
 *
 * Hand-rolled rather than a combobox library, for the reason the rest of the app is:
 * this is one screen with one list, and the dependency would be larger than the file.
 */

const OTHER = "อื่นๆ (ระบุเอง)";

export function SearchableSelect({
  id,
  label,
  options,
  value,
  onChange,
  placeholder,
  otherPlaceholder,
  hint,
}: {
  id: string;
  label: string;
  options: readonly string[];
  /** The stored value — a list entry, or whatever was typed under "อื่นๆ". */
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  otherPlaceholder: string;
  hint?: string;
}) {
  const [open, setOpen] = useState(false);
  // A value that is not on the list came from "อื่นๆ" — which is also how a profile
  // filled in before this picker existed reopens in the right mode.
  const [custom, setCustom] = useState(() => value !== "" && !options.includes(value));
  const customInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (custom) customInput.current?.focus();
  }, [custom]);

  function choose(option: string) {
    setCustom(false);
    onChange(option);
    setOpen(false);
  }

  function chooseOther() {
    setCustom(true);
    // Cleared, not carried over: the previous pick is not an answer to "ระบุเอง", and
    // leaving it there would let it be saved as though it had been typed.
    onChange("");
    setOpen(false);
  }

  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-base font-semibold">
        {label}
      </label>

      <button
        id={id}
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        className="input-field flex items-center justify-between gap-2 text-left"
      >
        <span className={custom || value !== "" ? "" : "text-muted"}>
          {custom ? OTHER : value !== "" ? value : placeholder}
        </span>
        <span aria-hidden className="text-muted">
          ▾
        </span>
      </button>

      {custom ? (
        <input
          ref={customInput}
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={otherPlaceholder}
          aria-label={`${label} (ระบุเอง)`}
          className="input-field mt-2"
        />
      ) : null}

      {hint ? <p className="mt-2 text-sm text-muted">{hint}</p> : null}

      {open ? (
        <OptionSheet
          title={label}
          options={options}
          value={custom ? "" : value}
          onPick={choose}
          onPickOther={chooseOther}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </div>
  );
}

function OptionSheet({
  title,
  options,
  value,
  onPick,
  onPickOther,
  onClose,
}: {
  title: string;
  options: readonly string[];
  value: string;
  onPick: (option: string) => void;
  onPickOther: () => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const matches = needle
    ? options.filter((option) => option.toLowerCase().includes(needle))
    : options;

  return (
    <Modal title={title} onClose={onClose}>
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="พิมพ์เพื่อค้นหา"
        aria-label={`ค้นหา${title}`}
        className="input-field"
      />

      <ul className="mt-3 space-y-1">
        {matches.map((option) => (
          <li key={option}>
            <Option selected={option === value} onClick={() => onPick(option)}>
              {option}
            </Option>
          </li>
        ))}

        {matches.length === 0 ? (
          <li className="px-1 py-3 text-base text-muted">
            ไม่พบ &ldquo;{query.trim()}&rdquo; — เลือก {OTHER} เพื่อพิมพ์เอง
          </li>
        ) : null}

        {/* Never filtered out: the member who cannot find their unit is exactly the one
            who needs this option, and they will have typed something by then. */}
        <li className="border-t border-border pt-1">
          <Option selected={false} onClick={onPickOther}>
            {OTHER}
          </Option>
        </li>
      </ul>
    </Modal>
  );
}

function Option({
  children,
  selected,
  onClick,
}: {
  children: React.ReactNode;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={selected ? "true" : undefined}
      className={`flex min-h-12 w-full items-center rounded-control px-3 text-left text-base ${
        selected ? "bg-brand-tint font-semibold text-brand" : ""
      }`}
    >
      {children}
    </button>
  );
}
