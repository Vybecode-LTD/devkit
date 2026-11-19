/**
 * Ctrl K (or ⌘ K): jump to any admin page the person can see (K4 contract §2,
 * §4 item 6), the sidebar's pages in its order, found by their name or their
 * section's. A dialog with a combobox over the list (WAI-ARIA's combobox with
 * a listbox popup): typing narrows it, the arrows move through it, Enter
 * opens the page, Escape closes it. Content search waits for the search index
 * hook (contract §6).
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";

import type { SidebarGroup } from "../slots/sidebar";
import { Dialog } from "../ui/Dialog";

type Page = { label: string; to: string; section?: string };

export function pagesOf(groups: readonly SidebarGroup[]): Page[] {
  return groups.flatMap((group) =>
    group.items.map((item) => (group.label === undefined ? { label: item.label, to: item.to } : { label: item.label, to: item.to, section: group.label })),
  );
}

/** The pages whose name or section holds every word typed, in the sidebar's order. */
export function matching(pages: readonly Page[], typed: string): Page[] {
  const words = typed.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...pages];
  return pages.filter((page) => {
    const said = `${page.label} ${page.section ?? ""}`.toLowerCase();
    return words.every((word) => said.includes(word));
  });
}

export function JumpTo({ groups, onClose }: { groups: readonly SidebarGroup[]; onClose: () => void }) {
  const id = useId();
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [typed, setTyped] = useState("");
  const [active, setActive] = useState(0);
  const pages = useMemo(() => pagesOf(groups), [groups]);
  const found = matching(pages, typed);
  const at = found.length === 0 ? -1 : Math.min(active, found.length - 1);

  // After the dialog's own focus on its heading: the reader came to type.
  useEffect(() => {
    input.current?.focus();
  }, []);

  useEffect(() => {
    if (at < 0) return;
    document.getElementById(`${id}-${String(at)}`)?.scrollIntoView({ block: "nearest" });
  }, [at, id]);

  const go = (page: Page | undefined) => {
    if (!page) return;
    onClose();
    void navigate(page.to);
  };

  return (
    <Dialog title="Jump to a page" onClose={onClose}>
      <div className="mf-jump">
        <label htmlFor={`${id}-input`} className="mf-visually-hidden">
          Page name
        </label>
        <input
          ref={input}
          id={`${id}-input`}
          className="mf-input mf-jump-input"
          type="text"
          role="combobox"
          aria-expanded="true"
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          aria-activedescendant={at >= 0 ? `${id}-${String(at)}` : undefined}
          autoComplete="off"
          spellCheck={false}
          placeholder="Type a page's name"
          value={typed}
          onChange={(event) => {
            setTyped(event.target.value);
            setActive(0);
          }}
          onKeyDown={(event) => {
            const last = found.length - 1;
            if (event.key === "ArrowDown" && last >= 0) {
              event.preventDefault();
              setActive(at >= last ? 0 : at + 1);
            } else if (event.key === "ArrowUp" && last >= 0) {
              event.preventDefault();
              setActive(at <= 0 ? last : at - 1);
            } else if (event.key === "Enter") {
              event.preventDefault();
              go(found[at]);
            }
          }}
        />
        <ul id={`${id}-list`} role="listbox" aria-label="Pages" className="mf-jump-list">
          {found.map((page, n) => (
            <li
              key={page.to}
              id={`${id}-${String(n)}`}
              role="option"
              aria-selected={n === at}
              className="mf-jump-option"
              onClick={() => {
                go(page);
              }}
              onPointerMove={() => {
                if (n !== at) setActive(n);
              }}
            >
              <span className="mf-jump-label">{page.label}</span>
              {page.section ? (
                <>
                  {" "}
                  <span className="mf-jump-section">{page.section}</span>
                </>
              ) : null}
            </li>
          ))}
        </ul>
        {/* Always there, so a screen reader hears it change. */}
        <p className="mf-jump-none" role="status">
          {found.length === 0 ? "No page's name has those words." : ""}
        </p>
      </div>
    </Dialog>
  );
}
