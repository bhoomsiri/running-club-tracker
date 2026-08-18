"use client";

import { useState } from "react";

import { Modal } from "@/components/modal";
import { SHIRT_SIZE_CHART, SHIRT_SIZES } from "@/lib/shirt-sizes";
import type { ShirtSize } from "@/lib/types";

/**
 * Which finisher shirt to order.
 *
 * A native `<select>` here, unlike the unit and job pickers: nine short options are what
 * the phone's own wheel is good at, and there is nothing to search.
 *
 * The size chart is beside the field rather than in a help page, because "L" means a
 * different shirt at every printer and the only way to choose right is to read the
 * measurements while choosing. Everyone gets one shirt from one print run, so a size
 * picked carelessly here is a shirt that does not fit for the whole year.
 */
export function ShirtSizeField({
  value,
  onChange,
}: {
  value: ShirtSize | "";
  onChange: (value: ShirtSize | "") => void;
}) {
  const [chartOpen, setChartOpen] = useState(false);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <label htmlFor="shirt-size" className="text-base font-semibold">
          ไซส์เสื้อ
        </label>
        <button
          type="button"
          onClick={() => setChartOpen(true)}
          className="tap shrink-0 text-base font-semibold text-brand underline"
        >
          ตารางไซส์
        </button>
      </div>

      <select
        id="shirt-size"
        value={value}
        onChange={(event) => onChange(event.target.value as ShirtSize | "")}
        className="input-field"
      >
        <option value="">เลือกไซส์</option>
        {SHIRT_SIZES.map((size) => (
          <option key={size} value={size}>
            {size}
          </option>
        ))}
      </select>

      <p className="mt-2 text-sm text-muted">
        ใช้สั่งเสื้อ finisher ของกิจกรรม — กดดูตารางไซส์ก่อนเลือก เพราะสั่งผลิตรอบเดียว
      </p>

      {chartOpen ? (
        <Modal title="ตารางไซส์เสื้อ" onClose={() => setChartOpen(false)}>
          <SizeChart selected={value} />
        </Modal>
      ) : null}
    </div>
  );
}

function SizeChart({ selected }: { selected: ShirtSize | "" }) {
  return (
    <>
      {/* The table is narrow enough for a phone, but its own scroller means a wider
          phone font or a longer heading cannot push the page sideways. */}
      <div className="overflow-x-auto">
        <table className="w-full text-base">
          <thead>
            <tr className="border-b border-border text-left">
              <th scope="col" className="py-2 pr-3 font-semibold">
                ไซส์
              </th>
              <th scope="col" className="py-2 pr-3 font-semibold">
                รอบอก (นิ้ว)
              </th>
              <th scope="col" className="py-2 font-semibold">
                ความยาว (นิ้ว)
              </th>
            </tr>
          </thead>
          <tbody>
            {SHIRT_SIZE_CHART.map((row) => (
              <tr
                key={row.size}
                className={`border-b border-border last:border-0 ${
                  row.size === selected ? "bg-brand-tint font-semibold text-brand" : ""
                }`}
              >
                <th scope="row" className="py-3 pr-3 text-left font-semibold">
                  {row.size}
                </th>
                <td className="py-3 pr-3 tabular-nums">{row.chestInches}</td>
                <td className="py-3 tabular-nums">{row.lengthInches}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-sm text-muted">
        รอบอกวัดแบบวางราบแล้วคูณสอง หากอยู่ระหว่างสองไซส์ แนะนำให้เลือกไซส์ที่ใหญ่กว่า
      </p>
    </>
  );
}
