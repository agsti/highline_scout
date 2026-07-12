import { useI18n } from "@/lib/i18n";
import { tealShade } from "@/lib/map-style";

// Same ramp the density cells are painted with, sampled low → high.
const RAMP = `linear-gradient(to right, ${tealShade(0)}, ${tealShade(0.45)}, ${tealShade(0.75)}, ${tealShade(1)})`;

export function LineChanceMeter() {
  const { t } = useI18n();

  return (
    <div
      data-testid="line-chance-meter"
      className="pointer-events-auto flex items-center gap-2.5 whitespace-nowrap rounded-full bg-card/95 px-3.5 py-[7px] shadow-pill backdrop-blur-[8px]"
    >
      <span className="text-[11px] font-bold text-primary-deep">{t("lineDensity")}</span>
      <span className="flex items-center gap-1.5">
        <span className="text-[10px] text-muted-foreground">{t("sparse")}</span>
        <span
          aria-hidden
          className="h-2 w-[84px] rounded border border-foreground/10"
          style={{ backgroundImage: RAMP }}
        />
        <span className="text-[10px] text-muted-foreground">{t("dense")}</span>
      </span>
    </div>
  );
}
