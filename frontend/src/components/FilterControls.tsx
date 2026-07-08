import type { Region } from "@/types/highliner";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { useI18n } from "@/lib/i18n";

interface FilterControlsProps {
  regions: Region[];
  region: string;
  maxLen: number;
  minExposure: number;
  showAnchors: boolean;
  onRegionChange: (region: string) => void;
  onMaxLenChange: (value: number) => void;
  onMaxLenCommit: (value: number) => void;
  onMinExposureChange: (value: number) => void;
  onMinExposureCommit: (value: number) => void;
  onShowAnchorsChange: (value: boolean) => void;
}

export function FilterControls(props: FilterControlsProps) {
  const { t } = useI18n();

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>{t("region")}</Label>
        <Select value={props.region} onValueChange={props.onRegionChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {props.regions.map((region) => (
              <SelectItem key={region.name} value={region.name}>
                {region.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <Label>{t("maxLength")}</Label>
          <span className="text-muted-foreground">{props.maxLen} m</span>
        </div>
        <Slider
          min={20}
          max={500}
          step={1}
          value={[props.maxLen]}
          onValueChange={([value]) => props.onMaxLenChange(value)}
          onValueCommit={([value]) => props.onMaxLenCommit(value)}
        />
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <Label>{t("minExposure")}</Label>
          <span className="text-muted-foreground">{props.minExposure} m</span>
        </div>
        <Slider
          min={0}
          max={300}
          step={1}
          value={[props.minExposure]}
          onValueChange={([value]) => props.onMinExposureChange(value)}
          onValueCommit={([value]) => props.onMinExposureCommit(value)}
        />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={props.showAnchors}
          onCheckedChange={(value) => props.onShowAnchorsChange(value === true)}
        />
        <span>{t("showAnchors")}</span>
      </label>
    </div>
  );
}
