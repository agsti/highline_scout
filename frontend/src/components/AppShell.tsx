import type { ReactNode } from "react";

interface AppShellProps {
  map: ReactNode;
  chrome: ReactNode;
}

// The map is full-bleed; every control floats above it (see MapChrome).
export function AppShell({ map, chrome }: AppShellProps) {
  return (
    <div className="relative h-dvh overflow-hidden bg-background text-foreground">
      <main className="absolute inset-0">{map}</main>
      {chrome}
    </div>
  );
}
