import { useEffect } from "react";

export const ERROR_TOAST_MS = 5000;

interface ErrorToastProps {
  message: string;
  eventId: number;
  onDismiss: (eventId: number) => void;
}

export function ErrorToast({ message, eventId, onDismiss }: ErrorToastProps) {
  useEffect(() => {
    if (!message) return;
    const timeout = window.setTimeout(() => onDismiss(eventId), ERROR_TOAST_MS);
    return () => window.clearTimeout(timeout);
  }, [message, eventId, onDismiss]);

  if (!message) return null;

  return (
    <div
      role="alert"
      className="pointer-events-none absolute left-1/2 top-[78px] z-[1100] max-w-[calc(100%-2rem)] -translate-x-1/2 rounded-lg bg-destructive px-4 py-2 text-center text-sm font-semibold text-destructive-foreground shadow-lg"
    >
      {message}
    </div>
  );
}
