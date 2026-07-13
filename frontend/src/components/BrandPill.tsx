export function BrandPill() {
  return (
    <div className="flex items-center gap-2 rounded-full bg-card/[0.94] py-0.5 pl-1 pr-3.5 shadow-pill backdrop-blur-[8px] md:pr-4 md:shadow-pill-lg">
      <img
        alt="Highline Scout"
        className="h-9 w-auto md:h-[38px]"
        src="/assets/logo.svg"
      />
    </div>
  );
}
