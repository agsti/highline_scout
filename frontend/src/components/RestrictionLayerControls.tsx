import type { RestrictionLayerMeta } from "@/types/highliner";
import { Checkbox } from "@/components/ui/checkbox";
import { restrictionText, useI18n } from "@/lib/i18n";

interface RestrictionLayerControlsProps {
  layers: RestrictionLayerMeta[];
  enabled: string[];
  onEnabledChange: (enabled: string[]) => void;
}

function HighlightedText({ text, highlight }: { text: string; highlight: string }) {
  const index = highlight ? text.indexOf(highlight) : -1;
  if (index < 0) return <>{text}</>;

  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded bg-yellow-100 px-0.5 font-semibold text-inherit">{highlight}</mark>
      {text.slice(index + highlight.length)}
    </>
  );
}

export function RestrictionLayerControls({
  layers,
  enabled,
  onEnabledChange,
}: RestrictionLayerControlsProps) {
  const { lang, t } = useI18n();

  return (
    <fieldset className="space-y-3 rounded-md border p-3">
      <legend className="px-1 text-xs font-medium text-muted-foreground">{t("restrictions")}</legend>
      {layers.map((layer) => {
        const checked = enabled.includes(layer.id);
        const tx = restrictionText(layer.id, lang, layer);

        return (
          <div key={layer.id} className="space-y-1">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={checked}
                onCheckedChange={(value) => {
                  const next = value === true ? [...enabled, layer.id] : enabled.filter((id) => id !== layer.id);
                  onEnabledChange(next);
                }}
              />
              <span className="h-3 w-3 border" style={{ backgroundColor: layer.color }} />
              <span>{tx.label}</span>
            </label>
            {checked && (
              <p className="pl-7 text-xs leading-5 text-muted-foreground">
                <HighlightedText text={tx.tooltip} highlight={tx.highlight} />
              </p>
            )}
          </div>
        );
      })}
      <p className="text-xs text-muted-foreground mt-2">{t("restrictionCredit")}</p>
    </fieldset>
  );
}
