import { restrictionText, useI18n } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";

interface RestrictionLegendProps {
  layers: RestrictionLayerMeta[];
  enabled: string[];
}

export function RestrictionLegend({ layers, enabled }: RestrictionLegendProps) {
  const { lang, t } = useI18n();
  const visible = layers.filter((layer) => enabled.includes(layer.id));

  if (visible.length === 0) return null;

  return (
    <ul
      aria-label={t("restrictions")}
      data-testid="legend-chip"
      className="pointer-events-auto flex items-center gap-3 rounded-full bg-card/[0.92] px-3.5 py-1.5 shadow-pill backdrop-blur-[8px]"
    >
      {visible.map((layer) => (
        <li
          key={layer.id}
          className="flex items-center gap-1.5 whitespace-nowrap text-[11px] text-muted-foreground"
        >
          <span
            aria-hidden
            className="h-2.5 w-2.5 shrink-0 rounded-sm"
            style={{ backgroundColor: layer.color }}
          />
          {restrictionText(layer.id, lang, layer).label}
        </li>
      ))}
    </ul>
  );
}
