import { UserButton } from "@clerk/nextjs";

/** No nav: there is nowhere else to go until this is finished. */
export default function OnboardingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="border-b border-border">
        <div className="mx-auto flex min-h-14 max-w-xl items-center justify-between px-4 py-2">
          <span className="text-lg font-bold">ชมรมวิ่ง</span>
          <UserButton />
        </div>
      </header>
      <main className="mx-auto w-full max-w-xl flex-1 px-4 py-6">{children}</main>
    </>
  );
}
