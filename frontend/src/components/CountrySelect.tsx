import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useI18n } from "@/lib/i18n";
import type { CountryEntry } from "@/types/highliner";

interface CountrySelectProps {
  controlId: string;
  countries: CountryEntry[];
  country: string;
  onCountryChange: (country: string) => void;
  contentClassName?: string;
}

export function CountrySelect({
  controlId,
  countries,
  country,
  onCountryChange,
  contentClassName,
}: CountrySelectProps) {
  const { t } = useI18n();

  return (
    <div>
      <label
        htmlFor={controlId}
        className="text-[11px] font-[650] uppercase tracking-[0.04em] text-muted-foreground"
      >
        {t("country")}
      </label>
      <Select
        value={country}
        onValueChange={onCountryChange}
        disabled={countries.length === 0}
      >
        <SelectTrigger
          id={controlId}
          aria-label={t("country")}
          className="mt-1.5 h-8"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent className={contentClassName}>
          {countries.map((entry) => (
            <SelectItem key={entry.id} value={entry.id}>
              {entry.id}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
