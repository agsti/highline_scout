import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Info, Menu, MessageSquarePlus, ShieldAlert, X } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useI18n } from "@/lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface NavMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAbout: () => void;
  onSafety: () => void;
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

export function NavMenu({ open, onOpenChange, onAbout, onSafety }: NavMenuProps) {
  const { t } = useI18n();
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
          className="flex h-[42px] w-[42px] items-center justify-center rounded-full bg-primary-deep text-primary-foreground shadow-menu-button transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          {open ? (
            <X className="h-4 w-4" strokeWidth={1.6} aria-hidden />
          ) : (
            <Menu className="h-4 w-4" strokeWidth={1.6} aria-hidden />
          )}
        </PopoverTrigger>

        <PopoverContent className="w-[248px] p-0" aria-label={t("menu")}>
          <div className="p-1.5">
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
            <MenuItem
              icon={<ShieldAlert className="h-4 w-4" />}
              label={t("safety")}
              onClick={() => select(onSafety)}
            />
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-hairline px-3.5 py-2.5">
            <span className="text-[11px] font-[650] uppercase tracking-[0.04em] text-muted-foreground">
              {t("language")}
            </span>
            <LanguageSwitcher variant="segmented" />
          </div>
        </PopoverContent>
      </Popover>
    </>
  );
}
