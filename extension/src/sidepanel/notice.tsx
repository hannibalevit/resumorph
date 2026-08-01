import { useCallback, useState } from "react";

/**
 * Status line shared by Onboarding and Settings. Both used to render everything
 * through the neutral `.status` block, so a failed connection test looked exactly
 * like normal progress — the tone is what tells the two apart, visually and for
 * screen readers (`alert` is announced assertively, `status` politely).
 */
export type NoticeTone = "info" | "error";
export type Notice = { text: string; tone: NoticeTone };

export function useNotice(initialText = "") {
  const [notice, setNotice] = useState<Notice>({ text: initialText, tone: "info" });
  const notify = useCallback((text: string) => setNotice({ text, tone: "info" }), []);
  const notifyError = useCallback((text: string) => setNotice({ text, tone: "error" }), []);
  return { notice, notify, notifyError };
}

export function NoticeLine({ notice }: { notice: Notice }) {
  if (!notice.text) return null;
  const isError = notice.tone === "error";
  return <p className={isError ? "status error" : "status"} role={isError ? "alert" : "status"}>{notice.text}</p>;
}
