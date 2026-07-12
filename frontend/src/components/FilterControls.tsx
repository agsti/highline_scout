import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { useI18n } from "@/lib/i18n";

export type LengthRange = [min: number, max: number];

interface FilterControlsProps {
  lengthRange: LengthRange;
  minExposure: number;
  showAnchors: boolean;
  canApply: boolean;
  onLengthRangeChange: (value: LengthRange) => void;
  onMinExposureChange: (value: number) => void;
  onShowAnchorsChange: (value: boolean) => void;
  onApply: () => void;
}

export function FilterControls(props: FilterControlsProps) {
  const { t } = useI18n();
  const [minLen, maxLen] = props.lengthRange;

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        props.onApply();
      }}
    >
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm md:text-xs">
          <Label className="md:font-semibold">{t("lineLength")}</Label>
          <span className="text-muted-foreground">
            {minLen}–{maxLen} m
          </span>
        </div>
        <Slider
          min={20}
          max={500}
          step={1}
          minStepsBetweenThumbs={1}
          value={props.lengthRange}
          onValueChange={([min, max]) => props.onLengthRangeChange([min, max])}
        />
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm md:text-xs">
          <Label className="md:font-semibold">{t("minExposure")}</Label>
          <span className="text-muted-foreground">{props.minExposure} m</span>
        </div>
        <Slider
          min={0}
          max={300}
          step={1}
          value={[props.minExposure]}
          onValueChange={([value]) => props.onMinExposureChange(value)}
        />
      </div>
      <label className="flex items-center gap-2 text-sm md:text-[13px]">
        <Checkbox
          checked={props.showAnchors}
          onCheckedChange={(value) => props.onShowAnchorsChange(value === true)}
        />
        <span>{t("showAnchors")}</span>
      </label>
      <Button type="submit" className="w-full md:h-9 md:rounded-lg md:text-[13px] md:font-bold" disabled={!props.canApply}>
        {t("applyFilters")}
      </Button>
    </form>
  );
}
