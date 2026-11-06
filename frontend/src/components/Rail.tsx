import { useEffect, useRef, useState, type ReactNode } from "react";
import { initials } from "../settings";
import type { User } from "../types";
import { BrandMark, Icon } from "./Art";

export type View = "chat" | "content" | "research" | "export";

const ITEMS: { id: View; label: string; icon: ReactNode }[] = [
  { id: "chat", label: "Chat", icon: <Icon.Bubble size={21} /> },
  { id: "content", label: "Content", icon: <Icon.Doc size={21} /> },
  { id: "research", label: "Research", icon: <Icon.Search size={21} /> },
  { id: "export", label: "Export", icon: <Icon.Download size={21} /> },
];

interface Props {
  user: User;
  view: View;
  counts: Partial<Record<View, number>>;
  voiceOpen: boolean;
  onSelect: (v: View) => void;
  onToggleVoice: () => void;
  onOpenAdmin: () => void;
  onSignOut: () => void;
}

/** Narrow icon rail: workspace views on top, the signed-in account at the bottom. */
export function Rail({ user, view, counts, voiceOpen, onSelect, onToggleVoice, onOpenAdmin, onSignOut }: Props) {
  return (
    <nav className="rail" aria-label="Workspace">
      <span className="rail__brand" title="ContentBlitz">
        <BrandMark size={24} />
        <span className="sr-only">ContentBlitz</span>
      </span>
      <ul className="rail__items">
        {ITEMS.map((it) => (
          <li key={it.id}>
            <button
              type="button"
              className="rail__btn"
              aria-label={it.label}
              aria-current={view === it.id ? "page" : undefined}
              data-tip={it.label}
              onClick={() => onSelect(it.id)}
            >
              {it.icon}
              {counts[it.id] ? <span className="rail__count" aria-hidden="true">{counts[it.id]}</span> : null}
            </button>
          </li>
        ))}
        <li>
          <button
            type="button"
            className="rail__btn"
            aria-label="Brand voice"
            aria-pressed={voiceOpen}
            data-tip="Brand voice"
            onClick={onToggleVoice}
          >
            <Icon.Voice size={21} />
          </button>
        </li>
      </ul>
      <AccountMenu user={user} onOpenAdmin={onOpenAdmin} onSignOut={onSignOut} />
    </nav>
  );
}

function AccountMenu({ user, onOpenAdmin, onSignOut }: { user: User; onOpenAdmin: () => void; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="account-menu" ref={box}>
      <button
        type="button"
        className="rail__avatar"
        aria-label={`Account: ${user.name}`}
        aria-haspopup="menu"
        aria-expanded={open}
        data-tip={user.name}
        onClick={() => setOpen((o) => !o)}
      >
        {initials(user.name)}
      </button>
      {open && (
        <div className="popover account-menu__pop" role="menu" aria-label="Account">
          <div className="account-menu__who">
            <span className="account__avatar" aria-hidden="true">{initials(user.name)}</span>
            <span className="account__who">
              <strong className="account__name">{user.name}</strong>
              <span className="account__email">{user.email}</span>
            </span>
          </div>
          {user.is_admin && (
            <button
              type="button"
              role="menuitem"
              className="popover__item"
              onClick={() => {
                setOpen(false);
                onOpenAdmin();
              }}
            >
              <Icon.Gauge /> Admin dashboard
            </button>
          )}
          <button type="button" role="menuitem" className="popover__item" onClick={onSignOut}>
            <Icon.Logout /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}
