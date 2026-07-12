export function BrandPill() {
  return (
    <div className="flex items-center gap-2 rounded-full bg-card/[0.94] py-[7px] pl-2 pr-3.5 shadow-pill backdrop-blur-[8px] md:py-2 md:pl-[9px] md:pr-4 md:shadow-pill-lg">
      <span
        aria-hidden
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-[10px] font-extrabold text-primary-foreground md:h-[26px] md:w-[26px]"
      >
        HS
      </span>
      <h1 className="text-[15px] font-bold tracking-[-0.01em] text-primary-deep md:text-base">
        Highline Scout
      </h1>
    </div>
  );
}
