/** Sign-in and sign-up: no nav, nothing to navigate to yet. */
export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-10">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">ชมรมวิ่ง</h1>
        <p className="mt-1 text-sm text-muted">บันทึกระยะวิ่ง สะสมแต้ม แลกของรางวัล</p>
      </div>
      {children}
    </main>
  );
}
