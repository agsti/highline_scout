import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { NavBar } from "./NavBar";

interface AppShellProps {
  sidebar: ReactNode;
  mobileControls: ReactNode;
  map: ReactNode;
}

export function AppShell({ sidebar, mobileControls, map }: AppShellProps) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(false);
  const expanded = !collapsed;

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground">
      <NavBar />
      <div className="relative flex-1 overflow-hidden">
        <aside
          className={cn(
            "absolute inset-y-0 left-0 z-[1000] hidden w-80 flex-col border-r bg-card shadow-sm transition-transform duration-200 md:flex",
            collapsed && "-translate-x-80",
          )}
        >
          {sidebar}
        </aside>
        <Button
          type="button"
          size="icon"
          variant="outline"
          aria-label={expanded ? t("panelMinimize") : t("panelExpand")}
          aria-expanded={expanded}
          className={cn(
            "absolute top-1/2 z-[1100] hidden h-14 w-8 -translate-y-1/2 rounded-l-none rounded-r-md bg-card md:inline-flex",
            expanded ? "left-80 -ml-px" : "left-0",
          )}
          onClick={() => setCollapsed((value) => !value)}
        >
          {expanded ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
        </Button>
        <main className={cn("h-full transition-[padding] duration-200 md:pl-80", collapsed && "md:pl-0")}>
          {map}
        </main>
        <div className="md:hidden">{mobileControls}</div>
      </div>
    </div>
  );
}
