import { UserButton } from "@clerk/nextjs";

import { BottomNav } from "@/components/bottom-nav";

/**
 * The signed-in shell. Everything in this route group is behind the middleware, so a
 * signed-out visitor never reaches these layouts at all.
 */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <span className="font-semibold">ชมรมวิ่ง</span>
          <UserButton />
        </div>
      </header>

      <BottomNav />

      {/* Bottom padding clears the fixed nav on phones; it is static from `sm` up. */}
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 pb-24 sm:pb-6">
        {children}
      </main>
    </>
  );
}
