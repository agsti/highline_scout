import { LanguageSwitcher } from "./LanguageSwitcher";

export function NavBar() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b bg-card px-3 md:px-4">
      <h1 className="text-base font-semibold tracking-tight md:text-lg">Highline Scout</h1>
      <LanguageSwitcher compact />
    </header>
  );
}
