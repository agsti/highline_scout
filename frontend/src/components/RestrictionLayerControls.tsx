import { CircleHelp } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { restrictionText, useI18n } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";

interface RestrictionLayerControlsProps {
  layers: RestrictionLayerMeta[];
  enabled: string[];
  country?: string;
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
  country = "spain",
  onEnabledChange,
}: RestrictionLayerControlsProps) {
  const { lang, t } = useI18n();
  const [activeDefinitionId, setActiveDefinitionId] = useState<string | null>(null);
  const definitionCardId = `${useId()}-restriction-definition`;
  const rootRef = useRef<HTMLFieldSetElement>(null);
  const activeLayer = layers.find((layer) => layer.id === activeDefinitionId);
  const activeText = activeLayer ? restrictionText(activeLayer.id, lang, activeLayer) : null;

  useEffect(() => {
    if (!activeDefinitionId) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setActiveDefinitionId(null);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [activeDefinitionId]);

  return (
    <fieldset
      ref={rootRef}
      className="space-y-3 rounded-md border p-3 md:rounded-none md:border-0 md:p-0"
    >
      <legend className="px-1 text-xs font-medium text-muted-foreground md:sr-only">
        {t("restrictions")}
      </legend>
      {layers.map((layer) => {
        const checked = enabled.includes(layer.id);
        const tx = restrictionText(layer.id, lang, layer);

        return (
          <div key={layer.id} className="space-y-1.5">
            <div className="flex items-center gap-2">
              <label className="flex min-w-0 flex-1 items-center gap-2 text-sm">
                <Checkbox
                  checked={checked}
                  onCheckedChange={(value) => {
                    const next =
                      value === true
                        ? [...enabled, layer.id]
                        : enabled.filter((id) => id !== layer.id);
                    onEnabledChange(next);
                  }}
                />
                <span className="h-3 w-3 shrink-0 border" style={{ backgroundColor: layer.color }} />
                <span>{tx.label}</span>
              </label>
              <button
                type="button"
                aria-label={t("restrictionInfo", { name: tx.label })}
                aria-expanded={activeDefinitionId === layer.id}
                aria-controls={activeDefinitionId === layer.id ? definitionCardId : undefined}
                onClick={() =>
                  setActiveDefinitionId((current) => (current === layer.id ? null : layer.id))
                }
                className="hidden h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring md:flex"
              >
                <CircleHelp className="h-4 w-4" aria-hidden />
              </button>
            </div>
            {checked ? (
              <p
                data-testid="mobile-restriction-definition"
                className="pl-7 text-xs leading-5 text-muted-foreground md:hidden"
              >
                <HighlightedText text={tx.tooltip} highlight={tx.highlight} />
              </p>
            ) : null}
          </div>
        );
      })}
      <p className="mt-2 text-xs text-muted-foreground">
        {t(country === "switzerland" ? "restrictionCreditSwitzerland" : "restrictionCredit")}
      </p>
      {activeLayer && activeText ? (
        <div
          id={definitionCardId}
          role="dialog"
          aria-labelledby={`${definitionCardId}-title`}
          className="absolute left-[calc(100%+1rem)] top-0 hidden w-[296px] rounded-[14px] border border-hairline-soft bg-card/[0.97] p-4 shadow-panel backdrop-blur-[10px] md:block"
        >
          <h3 id={`${definitionCardId}-title`} className="text-sm font-bold text-primary-deep">
            {activeText.label}
          </h3>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            <HighlightedText text={activeText.tooltip} highlight={activeText.highlight} />
          </p>
        </div>
      ) : null}
    </fieldset>
  );
}
