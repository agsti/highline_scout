import { describe, expect, it } from "vitest";
import { STRINGS, type StringKey } from "@/lib/i18n";
import { anchorPopupHtml, densityTooltipHtml, zonePopupHtml } from "./popups";

function t(key: StringKey, params?: Record<string, string | number>) {
  let value = STRINGS.en[key];
  if (!params) return value;
  return value.replace(/\{(\w+)\}/g, (match, name) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match,
  );
}

describe("popups", () => {
  it("builds zone popup html from zone properties", () => {
    expect(
      zonePopupHtml(
        {
          height_min: 31,
          height_max: 48,
          length_min: 101.2,
          length_max: 149.7,
          n_anchors: 4,
          n_pairs: 3,
        },
        t,
      ),
    ).toBe("height 31–48 m<br>length 101–150 m<br>4 anchors · 3 lines");
  });

  it("includes the density length hint only when min and max lengths are present", () => {
    expect(
      densityTooltipHtml(
        { n_pairs: 6, max_exposure: 72.4, length_min: 80.1, length_max: 121.9 },
        t,
      ),
    ).toBe("6 candidate lines · up to 72 m · 80–122 m long");

    expect(
      densityTooltipHtml(
        { n_pairs: 6, max_exposure: 72.4, length_min: null, length_max: null },
        t,
      ),
    ).toBe("6 candidate lines · up to 72 m");
  });

  it("builds anchor popup html with one translated line per sector", () => {
    expect(
      anchorPopupHtml(
        { elev: 1337.4, sectors: [[5.2, 24.6, 32.2], [180.1, 225.4, 58.9]] },
        t,
      ),
    ).toBe("anchor • elev 1337 m<br>drop 5–25° (32 m)<br>drop 180–225° (59 m)");
  });
});
