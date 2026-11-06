/** ContentBlitz illustrations and icons: original artwork, one soft "object" per agent. */
import type { ReactNode, SVGProps } from "react";

export type AgentKey = "query_handler" | "research" | "strategist" | "blog" | "linkedin" | "image";

/** The brand mark: a brush-stroke lightning bolt. */
export function BrandMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" className={`brandmark ${className}`}>
      <path
        d="M27.5 4.5 11 26.5h11.5L19 43.5 37 19.5H25.5l2-15Z"
        fill="var(--accent)"
        stroke="var(--accent)"
        strokeWidth="3.2"
        strokeLinejoin="round"
      />
      <path d="M26 9.5 15.5 24" stroke="rgb(255 255 255 / 0.45)" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

function Obj({ size, label, children }: { size: number; label?: string; children: ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className="obj" role={label ? "img" : undefined}
      aria-label={label} aria-hidden={label ? undefined : true}>
      {children}
    </svg>
  );
}

/** Soft, slightly 3D objects. Gradients are defined inline so each SVG stands alone. */
export function AgentObject({ agent, size = 56, label }: { agent: AgentKey; size?: number; label?: string }) {
  const id = `g-${agent}`;
  switch (agent) {
    case "query_handler": // a compass: reads the brief and finds direction
      return (
        <Obj size={size} label={label}>
          <defs>
            <radialGradient id={id} cx="35%" cy="30%" r="75%">
              <stop offset="0" stopColor="#f3f5f8" /><stop offset="1" stopColor="#b9c1cf" />
            </radialGradient>
          </defs>
          <ellipse cx="32" cy="56" rx="17" ry="3.5" fill="rgb(0 0 0 / 0.08)" />
          <circle cx="32" cy="30" r="22" fill={`url(#${id})`} />
          <circle cx="32" cy="30" r="16" fill="#fff" />
          <path d="M32 16 36 30 32 44 28 30Z" fill="#e2574c" />
          <path d="M32 30 36 30 32 44 28 30Z" fill="#46506a" />
          <circle cx="32" cy="30" r="2.4" fill="#fff" />
        </Obj>
      );
    case "research": // magnifier
      return (
        <Obj size={size} label={label}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#6aa8ff" /><stop offset="1" stopColor="#1f5fd1" />
            </linearGradient>
          </defs>
          <ellipse cx="32" cy="57" rx="18" ry="3.5" fill="rgb(0 0 0 / 0.08)" />
          <path d="m40 38 13 13" stroke="#30384d" strokeWidth="7" strokeLinecap="round" />
          <circle cx="27" cy="26" r="18" fill={`url(#${id})`} />
          <circle cx="27" cy="26" r="12.5" fill="#dcebff" />
          <path d="M20 22a8 8 0 0 1 8-6" stroke="#fff" strokeWidth="3" strokeLinecap="round" fill="none" />
        </Obj>
      );
    case "strategist": // notebook with a bookmark
      return (
        <Obj size={size} label={label}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#ffe08a" /><stop offset="1" stopColor="#f2b53a" />
            </linearGradient>
          </defs>
          <ellipse cx="32" cy="57" rx="18" ry="3.5" fill="rgb(0 0 0 / 0.08)" />
          <rect x="14" y="8" width="36" height="44" rx="6" fill={`url(#${id})`} transform="rotate(-8 32 30)" />
          <g transform="rotate(-8 32 30)">
            <rect x="20" y="17" width="22" height="3" rx="1.5" fill="#fff8e1" />
            <rect x="20" y="24" width="18" height="3" rx="1.5" fill="#fff8e1" />
            <rect x="20" y="31" width="20" height="3" rx="1.5" fill="#fff8e1" />
            <path d="M40 8v14l-4-3-4 3V8Z" fill="#e2574c" />
          </g>
        </Obj>
      );
    case "blog": // fountain pen nib
      return (
        <Obj size={size} label={label}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#c7b5ff" /><stop offset="1" stopColor="#7b5ce0" />
            </linearGradient>
          </defs>
          <ellipse cx="32" cy="57" rx="16" ry="3.5" fill="rgb(0 0 0 / 0.08)" />
          <g transform="rotate(35 32 30)">
            <rect x="26" y="2" width="12" height="26" rx="5" fill="#30384d" />
            <path d="M24 28h16l-3 14-5 10-5-10Z" fill={`url(#${id})`} />
            <path d="M32 34v12" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
            <circle cx="32" cy="34" r="2" fill="#fff" />
          </g>
        </Obj>
      );
    case "linkedin": // a post bubble
      return (
        <Obj size={size} label={label}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#8be0c2" /><stop offset="1" stopColor="#2aa57d" />
            </linearGradient>
          </defs>
          <ellipse cx="32" cy="57" rx="18" ry="3.5" fill="rgb(0 0 0 / 0.08)" />
          <path d="M10 14a8 8 0 0 1 8-8h28a8 8 0 0 1 8 8v20a8 8 0 0 1-8 8H28l-10 9v-9a8 8 0 0 1-8-8Z" fill={`url(#${id})`} />
          <rect x="18" y="15" width="28" height="3.5" rx="1.75" fill="#eafff6" />
          <rect x="18" y="23" width="20" height="3.5" rx="1.75" fill="#eafff6" />
          <text x="40" y="35" fontSize="10" fontWeight="700" fill="#eafff6" fontFamily="system-ui">#</text>
        </Obj>
      );
    case "image": // a framed picture
      return (
        <Obj size={size} label={label}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#ffb4a2" /><stop offset="1" stopColor="#ef6f5a" />
            </linearGradient>
          </defs>
          <ellipse cx="32" cy="57" rx="18" ry="3.5" fill="rgb(0 0 0 / 0.08)" />
          <rect x="8" y="10" width="48" height="40" rx="8" fill="#fff" transform="rotate(6 32 30)" />
          <g transform="rotate(6 32 30)">
            <rect x="13" y="15" width="38" height="30" rx="5" fill={`url(#${id})`} />
            <circle cx="22" cy="23" r="4" fill="#fff3c4" />
            <path d="m13 40 12-11 9 8 6-5 11 9v1a3 3 0 0 1-3 3H16a3 3 0 0 1-3-3Z" fill="#b8423a" opacity="0.65" />
          </g>
        </Obj>
      );
  }
}

/* ---------------------------------------------------------------- icons */
type IconProps = SVGProps<SVGSVGElement> & { size?: number };
const base = (size: number): SVGProps<SVGSVGElement> => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.9,
  strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true,
});

export const Icon = {
  Plus: ({ size = 18, ...p }: IconProps) => <svg {...base(size)} {...p}><path d="M12 5v14M5 12h14" /></svg>,
  ArrowUp: ({ size = 18, ...p }: IconProps) => <svg {...base(size)} {...p}><path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" /></svg>,
  ArrowDown: ({ size = 16, ...p }: IconProps) => <svg {...base(size)} {...p}><path d="M12 5v14M5.5 12.5 12 19l6.5-6.5" /></svg>,
  ArrowLeft: ({ size = 18, ...p }: IconProps) => <svg {...base(size)} {...p}><path d="M19 12H5M11.5 5.5 5 12l6.5 6.5" /></svg>,
  Check: ({ size = 14, ...p }: IconProps) => <svg {...base(size)} strokeWidth={2.6} {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>,
  X: ({ size = 16, ...p }: IconProps) => <svg {...base(size)} {...p}><path d="M6 6l12 12M18 6 6 18" /></svg>,
  Menu: ({ size = 20, ...p }: IconProps) => <svg {...base(size)} {...p}><path d="M4 7h16M4 12h16M4 17h10" /></svg>,
  Copy: ({ size = 15, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><rect x="9" y="9" width="11" height="11" rx="3" /><path d="M15 9V7a3 3 0 0 0-3-3H7a3 3 0 0 0-3 3v5a3 3 0 0 0 3 3h2" /></svg>
  ),
  Chat: ({ size = 16, ...p }: IconProps) => <svg {...base(size)} {...p}><path d="M5 18.5V7a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3H8.5Z" /></svg>,
  Logout: ({ size = 16, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><path d="M14 4h3a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3h-3M10 16l-4-4 4-4M6 12h10" /></svg>
  ),
  Gauge: ({ size = 16, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><path d="M4.5 17a8 8 0 1 1 15 0" /><path d="m12 13 3.5-4" /></svg>
  ),
  Voice: ({ size = 16, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2" /></svg>
  ),
  Doc: ({ size = 20, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><path d="M7 3.5h7l4.5 4.5v11a1.5 1.5 0 0 1-1.5 1.5H7A1.5 1.5 0 0 1 5.5 19V5A1.5 1.5 0 0 1 7 3.5Z" /><path d="M13.5 3.5V8.5h5M9 12.5h6M9 16h4" /></svg>
  ),
  Search: ({ size = 20, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 4.5 4.5" /></svg>
  ),
  Download: ({ size = 20, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><path d="M12 4v10.5M7.5 10 12 14.5 16.5 10" /><path d="M5 15.5v2A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-2" /></svg>
  ),
  Bubble: ({ size = 20, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><path d="M12 4.5c4.7 0 8 2.9 8 6.6s-3.3 6.6-8 6.6c-.9 0-1.8-.1-2.6-.3L5 19.5l.9-3.5C4.7 14.8 4 13.1 4 11.1c0-3.7 3.3-6.6 8-6.6Z" /></svg>
  ),
  Dots: ({ size = 18, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><circle cx="5.5" cy="12" r="1.1" fill="currentColor" /><circle cx="12" cy="12" r="1.1" fill="currentColor" /><circle cx="18.5" cy="12" r="1.1" fill="currentColor" /></svg>
  ),
  Panel: ({ size = 18, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><rect x="3.5" y="4.5" width="17" height="15" rx="3" /><path d="M9.5 4.5v15" /></svg>
  ),
  Mail: ({ size = 18, ...p }: IconProps) => (
    <svg {...base(size)} {...p}><rect x="3.5" y="5.5" width="17" height="13" rx="3" /><path d="m4.5 7.5 7.5 6 7.5-6" /></svg>
  ),
};
