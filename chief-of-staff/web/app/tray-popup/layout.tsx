"use client";

export default function TrayPopupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="h-screen w-screen bg-surface-0 text-text-primary overflow-hidden select-none">
      {children}
    </div>
  );
}
