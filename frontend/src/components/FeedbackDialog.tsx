import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { capture } from "@/lib/analytics";
import { useI18n } from "@/lib/i18n";

interface FeedbackDialogProps { open: boolean; onOpenChange: (open: boolean) => void; }

export function FeedbackDialog({ open, onOpenChange }: FeedbackDialogProps) {
  const { t } = useI18n();
  const [topic, setTopic] = useState("other");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setSending(true); setError(false);
    try {
      const response = await fetch("/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ topic, message, reply_email: email || undefined }) });
      if (!response.ok) throw new Error();
      setSent(true); capture("feedback_submitted", { topic });
    } catch { setError(true); } finally { setSending(false); }
  }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent closeLabel={t("close")} className="z-[1210] max-w-md"><DialogHeader><DialogTitle>{t("feedback")}</DialogTitle></DialogHeader>{sent ? <div className="space-y-4 text-sm"><p>Thanks — your feedback was sent.</p><Button onClick={() => onOpenChange(false)}>{t("close")}</Button></div> : <form className="space-y-3" onSubmit={submit}><label className="grid gap-1 text-sm">{t("feedbackTopic")}<select value={topic} onChange={(event) => setTopic(event.target.value)} className="h-9 rounded-md border border-input bg-background px-2"><option value="bug">{t("feedbackTopicBug")}</option><option value="data">{t("feedbackTopicData")}</option><option value="idea">{t("feedbackTopicIdea")}</option><option value="other">{t("feedbackTopicOther")}</option></select></label><label className="grid gap-1 text-sm">Message<textarea required maxLength={4000} value={message} onChange={(event) => setMessage(event.target.value)} className="min-h-28 rounded-md border border-input bg-background p-2" /></label><label className="grid gap-1 text-sm">Reply email (optional)<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="h-9 rounded-md border border-input px-2" /></label>{error ? <p className="text-sm text-destructive">Could not send feedback. Try again.</p> : null}<Button type="submit" disabled={sending || !message.trim()}>{sending ? "Sending…" : t("feedback")}</Button></form>}</DialogContent></Dialog>;
}
