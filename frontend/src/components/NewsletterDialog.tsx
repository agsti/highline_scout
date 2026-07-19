import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { capture } from "@/lib/analytics";
import { useI18n } from "@/lib/i18n";

interface NewsletterDialogProps {
  open: boolean;
  onClose: () => void;
  onSubscribed: () => void;
  onDismissForever: () => void;
}

export function NewsletterDialog({ open, onClose, onSubscribed, onDismissForever }: NewsletterDialogProps) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSending(true);
    setError(false);
    try {
      const response = await fetch("/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!response.ok) throw new Error();
      capture("newsletter_signup");
      setDone(true);
      onSubscribed();
    } catch {
      setError(true);
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent closeLabel={t("close")} className="z-[1210] max-w-md">
        <DialogHeader>
          <DialogTitle>{t("newsletterHeading")}</DialogTitle>
        </DialogHeader>
        {done ? (
          <div className="space-y-4 text-sm">
            <p>{t("newsletterSuccess")}</p>
            <Button onClick={onClose}>{t("close")}</Button>
          </div>
        ) : (
          <form className="space-y-3" onSubmit={submit}>
            <p className="text-sm text-muted-foreground">{t("newsletterSubtext")}</p>
            <input
              type="email"
              required
              value={email}
              placeholder={t("newsletterEmailPlaceholder")}
              aria-label={t("newsletterEmailPlaceholder")}
              onChange={(event) => setEmail(event.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-2"
            />
            {error ? <p className="text-sm text-destructive">{t("newsletterError")}</p> : null}
            <div className="flex items-center justify-between gap-3">
              <Button type="submit" disabled={sending || !email.trim()}>
                {sending ? t("newsletterSending") : t("newsletterSubscribe")}
              </Button>
              <button
                type="button"
                onClick={onDismissForever}
                className="text-sm text-muted-foreground underline underline-offset-2"
              >
                {t("newsletterDontShow")}
              </button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
