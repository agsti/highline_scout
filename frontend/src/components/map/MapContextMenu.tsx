import { CopyIcon, ExternalLink } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

type T = ReturnType<typeof useI18n>["t"];

export interface ContextMenuPoint {
  lat: number;
  lng: number;
  zoom: number;
  x: number;
  y: number;
}

export async function copyViewportLink(
  lat: number,
  lng: number,
  zoom: number,
  t: T,
): Promise<void> {
  const params = new URLSearchParams({
    lat: lat.toFixed(5),
    lng: lng.toFixed(5),
    z: String(zoom),
  });
  const url = `${window.location.origin}${window.location.pathname}?${params}`;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(url);
    return;
  }
  window.prompt(t("copyLink"), url);
}

export function MapContextMenu(props: {
  point: ContextMenuPoint | null;
  t: T;
  onDismiss: () => void;
}): ReactElement | null {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!props.point) return;

    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && rootRef.current?.contains(event.target)) return;
      props.onDismiss();
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") props.onDismiss();
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [props.onDismiss, props.point]);

  if (!props.point) return null;

  const { point, t } = props;
  const googleMapsHref = `https://www.google.com/maps?q=${point.lat},${point.lng}`;

  async function copyLink() {
    await copyViewportLink(point.lat, point.lng, point.zoom, t);
    props.onDismiss();
  }

  return (
    <div ref={rootRef} className="pointer-events-none absolute inset-0 z-[1200]">
      <div
        data-testid="mobile-context-point-marker"
        className="pointer-events-none absolute left-1/2 top-1/2 h-10 w-10 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-primary bg-primary/15 shadow-[0_0_0_4px_hsl(var(--background)),0_0_0_8px_hsl(var(--primary)/0.35),0_8px_24px_hsl(var(--foreground)/0.35)] after:absolute after:left-1/2 after:top-1/2 after:h-3 after:w-3 after:-translate-x-1/2 after:-translate-y-1/2 after:rounded-full after:bg-primary after:shadow-[0_0_0_2px_hsl(var(--background))] md:hidden"
        aria-hidden="true"
      />
      <div
        data-testid="desktop-context-menu"
        className="pointer-events-auto absolute hidden min-w-56 overflow-hidden rounded-md border bg-background/98 p-1 text-sm shadow-xl backdrop-blur md:block"
        style={{ left: point.x, top: point.y }}
      >
        <a
          className="block rounded-sm px-3 py-2 font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          href={googleMapsHref}
          target="_blank"
          rel="noopener"
        >
          {t("viewInGoogleMaps")}
        </a>
        <button
          type="button"
          className="block w-full rounded-sm px-3 py-2 text-left font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          onClick={() => void copyLink()}
        >
          {t("copyLink")}
        </button>
      </div>

      <div
        data-testid="mobile-context-menu"
        className="pointer-events-auto fixed inset-0 z-[1200] flex items-end bg-black/35 p-3 md:hidden"
        onClick={props.onDismiss}
      >
        <div
          className="w-full rounded-xl border bg-background p-3 shadow-xl"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-border" />
          <h2 className="mb-3 px-1 text-sm font-semibold">{t("pointActions")}</h2>
          <div className="grid gap-2">
            <Button
              asChild
              type="button"
              variant="outline"
              className="h-11 w-full justify-start"
            >
              <a href={googleMapsHref} target="_blank" rel="noopener">
                <ExternalLink className="h-4 w-4" />
                {t("viewInGoogleMaps")}
              </a>
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-11 w-full justify-start"
              onClick={() => void copyLink()}
            >
              <CopyIcon className="h-4 w-4" />
              {t("copyLink")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
