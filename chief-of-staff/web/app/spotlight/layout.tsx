"use client";

export default function SpotlightLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="h-screen w-screen bg-transparent overflow-hidden select-none">
      {children}
    </div>
  );
}
