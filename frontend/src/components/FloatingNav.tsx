import { useState } from "react";
import { cn } from "@/lib/utils";
import { BrandPill } from "./BrandPill";
import { NavMenu } from "./NavMenu";

interface FloatingNavProps {
  onAbout: () => void;
  onSafety: () => void;
}

export function FloatingNav({ onAbout, onSafety }: FloatingNavProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header
      className={cn(
        "pointer-events-none absolute inset-x-3 top-3.5 flex items-center justify-between gap-2 md:inset-x-4 md:top-4",
        // The menu's scrim is portaled to body at z-1100, and this header is its
        // own stacking context — so the row has to outrank the scrim from here,
        // or the brand and the menu button would be dimmed along with the map.
        menuOpen ? "z-[1120]" : "z-[1000]",
      )}
    >
      <div className="pointer-events-auto">
        <BrandPill />
      </div>
      <div className="pointer-events-auto">
        <NavMenu
          open={menuOpen}
          onOpenChange={setMenuOpen}
          onAbout={onAbout}
          onSafety={onSafety}
        />
      </div>
    </header>
  );
}
