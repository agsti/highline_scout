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
    <ul aria-label={t("restrictions")} className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
      {visible.map((layer) => (
        <li key={layer.id} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            aria-hidden
            className="h-2.5 w-2.5 shrink-0 rounded-sm border"
            style={{ backgroundColor: layer.color }}
          />
          {restrictionText(layer.id, lang, layer).label}
        </li>
      ))}
    </ul>
  );
}
