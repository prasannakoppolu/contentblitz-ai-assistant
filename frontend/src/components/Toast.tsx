import { useCallback, useEffect, useRef, useState } from "react";

/** One short-lived status message at a time, announced to screen readers. */
export function useToast(ms = 3200) {
  const [text, setText] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const notify = useCallback(
    (t: string) => {
      clearTimeout(timer.current);
      setText(t);
      timer.current = setTimeout(() => setText(null), ms);
    },
    [ms],
  );
  useEffect(() => () => clearTimeout(timer.current), []);
  const node = (
    <div className="toast-region" aria-live="polite" role="status">
      {text && <div className="toast">{text}</div>}
    </div>
  );
  return [node, notify] as const;
}
