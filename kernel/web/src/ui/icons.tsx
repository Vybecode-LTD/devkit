/**
 * The kit's icon set (K4 contract change 10): line icons on a 24px grid,
 * drawn in `currentColor`, from the Vibrant Mindz admin boards (VM Website
 * `design/generators/admin_kit.py`) and its sign-in board. `IconName` is one of these names; the
 * slots' `icon` and `adminSections` take it.
 */
import type { ReactNode } from "react";

type Drawn = {
  /** The shapes inside the SVG. */
  body: ReactNode;
  /** Its size in pixels when none is asked for. */
  size: number;
  stroke: number;
  /** Filled, not stroked, on its own grid (the play triangle). */
  filled?: { viewBox: string };
};

const line = (body: ReactNode, size = 18, stroke = 1.8): Drawn => ({ body, size, stroke });

export const ICONS = {
  dashboard: line(
    <>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </>,
  ),
  home: line(
    <>
      <path d="M3 11l9-7 9 7" />
      <path d="M5 10v10h14V10" />
    </>,
  ),
  music: line(
    <>
      <path d="M9 18V5l11-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="17" cy="16" r="3" />
    </>,
  ),
  beats: line(<path d="M3 12h2l2-6 3 12 3-9 2 5 2-2h4" />),
  shop: line(
    <>
      <path d="M4 7h16l-1.5 11a2 2 0 0 1-2 1.8H7.5a2 2 0 0 1-2-1.8z" />
      <path d="M9 7a3 3 0 0 1 6 0" />
    </>,
  ),
  people: line(
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 20a6 6 0 0 1 12 0" />
      <circle cx="17" cy="9" r="2.6" />
      <path d="M15.5 14.2A5 5 0 0 1 21 19" />
    </>,
  ),
  chat: line(<path d="M4 5h16v11H9l-5 4z" />),
  document: line(
    <>
      <path d="M6 3h9l4 4v14H6z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h7M9 17h5" />
    </>,
  ),
  lock: line(
    <>
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </>,
  ),
  settings: line(
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </>,
  ),
  search: line(
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" />
    </>,
  ),
  bell: line(
    <>
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 8 3 8H3s3-1 3-8" />
      <path d="M10.5 20a1.7 1.7 0 0 0 3 0" />
    </>,
  ),
  external: line(
    <>
      <path d="M14 4h6v6" />
      <path d="M20 4l-9 9" />
      <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </>,
  ),
  grip: line(
    <>
      <circle cx="9" cy="6" r="1" />
      <circle cx="15" cy="6" r="1" />
      <circle cx="9" cy="12" r="1" />
      <circle cx="15" cy="12" r="1" />
      <circle cx="9" cy="18" r="1" />
      <circle cx="15" cy="18" r="1" />
    </>,
    16,
    2.2,
  ),
  plus: line(<path d="M12 5v14M5 12h14" />, 16, 2),
  close: line(<path d="M6 6l12 12M18 6L6 18" />, 14, 2),
  check: line(<path d="M5 12.5l4.5 4.5L19 7.5" />, 14, 2.4),
  "chevron-right": line(<path d="M9 6l6 6-6 6" />, 16, 2),
  "chevron-down": line(<path d="M6 9l6 6 6-6" />, 16, 2),
  calendar: line(
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </>,
    14,
  ),
  upload: line(
    <>
      <path d="M12 16V4" />
      <path d="M7 9l5-5 5 5" />
      <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
    </>,
    16,
  ),
  link: line(
    <>
      <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" />
      <path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
    </>,
    16,
  ),
  play: { body: <path d="M4.5 2.5 L13 8 L4.5 13.5 Z" />, size: 12, stroke: 0, filled: { viewBox: "0 0 16 16" } },
  warning: line(
    <>
      <path d="M12 3l9.5 17h-19z" />
      <path d="M12 10v4.5M12 17.5v.01" />
    </>,
    18,
    2,
  ),
  info: line(
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6M12 7.5v.01" />
    </>,
    18,
    2,
  ),
  shield: line(<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />),
  // The sign-in board's (VM Website design/site/Auth.dc.html): a passkey, and an emailed code.
  key: line(
    <>
      <circle cx="8" cy="15" r="4" />
      <path d="M10.8 12.2L20 3M16 7l3 3M14 9l2 2" />
    </>,
    20,
    1.9,
  ),
  mail: line(
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 7l9 6 9-6" />
    </>,
    20,
    1.9,
  ),
} as const satisfies Record<string, Drawn>;

/** An icon's name: one of the kit's set. */
export type IconName = keyof typeof ICONS;

export const ICON_NAMES = Object.keys(ICONS) as IconName[];
