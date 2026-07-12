import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface FiltersPanelProps {
  filters: ReactNode;
  restrictions: ReactNode;
  statuses: ReactNode;
}

export function FiltersPanel({ filters, restrictions, statuses }: FiltersPanelProps) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="absolute left-4 top-[76px] z-[1000] hidden w-[296px] md:block">
      <div
        data-testid="filters-card"
        className={cn(
          "rounded-[14px] bg-card/[0.97] shadow-panel backdrop-blur-[10px]",
          collapsed && "overflow-hidden",
        )}
      >
        <div className="flex items-center justify-between border-b border-hairline-soft px-3.5 py-[13px]">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-[15px] w-[15px] text-primary-deep" aria-hidden />
            <span className="text-[13px] font-bold text-primary-deep">{t("filters")}</span>
          </div>
          <button
            type="button"
            aria-label={collapsed ? t("panelExpand") : t("panelMinimize")}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((value) => !value)}
            className="flex h-[26px] w-[26px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <ChevronDown
              className={cn("h-3 w-3 transition-transform duration-200", collapsed && "-rotate-90")}
              aria-hidden
            />
          </button>
        </div>

        <div
          className={cn(
            "grid transition-[grid-template-rows] duration-200 ease-out",
            collapsed ? "grid-rows-[0fr]" : "grid-rows-[1fr]",
          )}
        >
          <div
            data-testid="filters-panel-content"
            className={cn(collapsed && "overflow-hidden")}
          >
            <div className="flex flex-col gap-3.5 p-3.5">
              {filters}
              {statuses}
            </div>

            <div className="relative border-t border-hairline-soft">
              <div className="px-3.5 pt-[11px] text-[13px] font-bold text-primary-deep">
                {t("restrictions")}
              </div>
              <div className="px-3.5 pb-3.5 pt-3">{restrictions}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
