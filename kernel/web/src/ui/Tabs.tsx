/**
 * Tabs (VM Website `admin_kit.py`, `.a-tab`; WAI-ARIA's tabs pattern): one
 * tab stop for the row, the arrow keys move along it and choose as they go,
 * Home and End go to the ends. Every panel stays drawn, the others hidden, so
 * what's typed in one survives a look at another.
 *
 * Give `selected` and `onSelect` to keep the choice yourself (in the address,
 * say); otherwise the tabs keep it, starting at the first.
 */
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export type TabItem = { id: string; label: ReactNode; panel: ReactNode };

export type TabsProps = {
  /** What the row of tabs is, for a screen reader: "Settings". */
  label: string;
  tabs: readonly TabItem[];
  selected?: string;
  onSelect?: (id: string) => void;
};

export function Tabs({ label, tabs, selected, onSelect }: TabsProps) {
  const base = useId();
  const [own, setOwn] = useState(tabs[0]?.id ?? "");
  const current = tabs.some((tab) => tab.id === (selected ?? own)) ? (selected ?? own) : (tabs[0]?.id ?? "");
  const buttons = useRef(new Map<string, HTMLButtonElement>());

  const choose = (id: string, focus: boolean) => {
    if (selected === undefined) setOwn(id);
    onSelect?.(id);
    if (focus) buttons.current.get(id)?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    // From the tab with the focus: a page keeping the choice may not have caught up yet (CodeRabbit on #82).
    const focused = tabs.findIndex((tab) => buttons.current.get(tab.id) === document.activeElement);
    const at = focused >= 0 ? focused : tabs.findIndex((tab) => tab.id === current);
    const last = tabs.length - 1;
    const to =
      event.key === "ArrowRight"
        ? at === last
          ? 0
          : at + 1
        : event.key === "ArrowLeft"
          ? at === 0
            ? last
            : at - 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? last
              : -1;
    const next = tabs[to];
    if (!next) return;
    event.preventDefault();
    choose(next.id, true);
  };

  return (
    <div className="mf-tabs">
      <div className="mf-tab-row" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
        {tabs.map((tab) => {
          const on = tab.id === current;
          return (
            <button
              key={tab.id}
              ref={(element) => {
                if (element) buttons.current.set(tab.id, element);
                else buttons.current.delete(tab.id);
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${tab.id}`}
              className="mf-tab"
              aria-selected={on}
              aria-controls={`${base}-panel-${tab.id}`}
              tabIndex={on ? 0 : -1}
              onClick={() => {
                choose(tab.id, false);
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${base}-panel-${tab.id}`}
          className="mf-tab-panel"
          aria-labelledby={`${base}-tab-${tab.id}`}
          hidden={tab.id !== current}
          tabIndex={0}
        >
          {tab.panel}
        </div>
      ))}
    </div>
  );
}
