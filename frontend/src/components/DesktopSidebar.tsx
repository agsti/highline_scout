import type { ReactNode } from "react";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface DesktopSidebarProps {
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
  caveat: string;
}

export function DesktopSidebar({ filters, restrictions, statuses, caveat }: DesktopSidebarProps) {
  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Highline Scout</h1>
      </div>
      {filters}
      {statuses}
      {restrictions}
      <p className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5 text-destructive">
        {caveat}
      </p>
      <div className="mt-auto border-t pt-4">
        <LanguageSwitcher />
      </div>
    </div>
  );
}
