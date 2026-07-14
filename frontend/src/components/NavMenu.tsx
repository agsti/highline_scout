import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Info, Map, Menu, MessageSquarePlus, X } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useI18n } from "@/lib/i18n";
import type { RestrictionAreaMode } from "@/types/highliner";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface NavMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAbout: () => void;
  restrictionAreaMode: RestrictionAreaMode;
  onRestrictionAreaModeChange: (mode: RestrictionAreaMode) => void;
}

interface MenuItemProps {
  icon: ReactNode;
  label: string;
  hint?: string;
  onClick: () => void;
}

function MenuItem({ icon, label, hint, onClick }: MenuItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-[44px] w-full items-center gap-2.5 rounded-[10px] px-2.5 py-[11px] text-left text-[13px] font-semibold text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <span aria-hidden className="flex shrink-0 text-muted-foreground">
        {icon}
      </span>
      <span className="flex-1">{label}</span>
      <span aria-live="polite" className="text-[11px] font-semibold text-muted-foreground">
        {hint ?? ""}
      </span>
    </button>
  );
}

const HOW_IT_WORKS_PATHS = {
  ca: "/ca/how-it-works",
  es: "/es/how-it-works",
  en: "/en/how-it-works",
} as const;

export function NavMenu({
  open,
  onOpenChange,
  onAbout,
  restrictionAreaMode,
  onRestrictionAreaModeChange,
}: NavMenuProps) {
  const { lang, t } = useI18n();
  const [feedbackNoted, setFeedbackNoted] = useState(false);

  function handleOpenChange(next: boolean) {
    if (!next) setFeedbackNoted(false);
    onOpenChange(next);
  }

  function select(action: () => void) {
    handleOpenChange(false);
    action();
  }

  return (
    <>
      {/* Portaled to body: the nav header is its own stacking context, so a
          scrim rendered inside it could never cover the map. */}
      {open
        ? createPortal(
            <div aria-hidden className="fixed inset-0 z-[1100] bg-[rgba(22,48,42,0.18)]" />,
            document.body,
          )
        : null}

      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger
          aria-label={t("menu")}
          className="flex items-center gap-2 rounded-full bg-card py-[7px] pl-2 pr-3.5 text-primary-deep shadow-pill transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring md:py-2 md:pl-[9px] md:pr-4 md:shadow-pill-lg"
        >
          <span className="text-[15px] font-bold tracking-[-0.01em] md:text-base">{t("menu")}</span>
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground md:h-[24px] md:w-[24px]">
            {open ? (
              <X className="h-4 w-4" strokeWidth={2.5} aria-hidden />
            ) : (
              <Menu className="h-4 w-4" strokeWidth={2.5} aria-hidden />
            )}
          </span>
        </PopoverTrigger>

        <PopoverContent className="w-[248px] p-0" aria-label={t("menu")}>
          <div className="px-3.5 py-2.5">
            <label
              htmlFor="restriction-area-mode"
              className="text-[11px] font-[650] uppercase tracking-[0.04em] text-muted-foreground"
            >
              {t("restrictionAreas")}
            </label>
            <Select value={restrictionAreaMode} onValueChange={onRestrictionAreaModeChange}>
              <SelectTrigger
                id="restriction-area-mode"
                aria-label={t("restrictionAreas")}
                className="mt-1.5 h-8"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="informative">{t("restrictionAreasInformative")}</SelectItem>
                <SelectItem value="exclude-overlaps">
                  {t("restrictionAreasExcludeOverlaps")}
                </SelectItem>
                <SelectItem value="exclude-inside">
                  {t("restrictionAreasExcludeInside")}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-hairline px-3.5 py-2.5">
            <span className="text-[11px] font-[650] uppercase tracking-[0.04em] text-muted-foreground">
              {t("language")}
            </span>
            <LanguageSwitcher variant="segmented" />
          </div>

          <div className="border-t border-hairline p-1.5">
            {/* For SEO: use a real link so the methodology page remains discoverable. */}
            <a
              href={HOW_IT_WORKS_PATHS[lang]}
              className="flex min-h-[44px] w-full items-center gap-2.5 rounded-[10px] px-2.5 py-[11px] text-left text-[13px] font-semibold text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <span aria-hidden className="flex shrink-0 text-muted-foreground">
                <Map className="h-4 w-4" />
              </span>
              <span className="flex-1">{t("howItWorksMenu")}</span>
            </a>
            <MenuItem
              icon={<MessageSquarePlus className="h-4 w-4" />}
              label={t("feedback")}
              hint={feedbackNoted ? t("feedbackComingSoon") : undefined}
              onClick={() => setFeedbackNoted(true)}
            />
            <MenuItem
              icon={<Info className="h-4 w-4" />}
              label={t("about")}
              onClick={() => select(onAbout)}
            />
          </div>
        </PopoverContent>
      </Popover>
    </>
  );
}
