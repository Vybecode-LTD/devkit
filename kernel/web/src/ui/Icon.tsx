/**
 * One of the kit's icons. Hidden from screen readers unless it's given a
 * `label`, since an icon beside words only repeats them; one standing alone
 * (an icon button's) needs the label, or the button its own.
 */
import { ICONS, type IconName } from "./icons";

export type IconProps = {
  name: IconName;
  /** Its size in pixels; each icon's own by default. */
  size?: number;
  /** What it means, when nothing beside it says so. */
  label?: string;
  className?: string;
};

export function Icon({ name, size, label, className }: IconProps) {
  const drawn: (typeof ICONS)[IconName] = ICONS[name];
  const px = size ?? drawn.size;
  const named = label ? { role: "img", "aria-label": label } : { "aria-hidden": true as const };
  const filled = "filled" in drawn ? drawn.filled : undefined;
  return (
    <svg
      className={className ? `mf-icon ${className}` : "mf-icon"}
      width={px}
      height={px}
      viewBox={filled ? filled.viewBox : "0 0 24 24"}
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={filled ? undefined : drawn.stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
      {...named}
    >
      {drawn.body}
    </svg>
  );
}
