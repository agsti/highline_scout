export function StatusLine({ children }: { children?: string }) {
  if (!children) return null;
  return <p className="text-xs leading-5 text-muted-foreground">{children}</p>;
}
