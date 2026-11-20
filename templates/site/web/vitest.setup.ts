import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom draws nothing, so it has no scrollIntoView; a browser always does.
Element.prototype.scrollIntoView = function scrollIntoView() {
  // Nothing to scroll.
};

// Nor a page to scroll: ScrollMemory's scrolls go nowhere.
window.scrollTo = function scrollTo() {
  // Nothing to scroll.
};

// Nor a modal dialog's top layer: opening one only sets `open`, as a browser's does.
HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
  this.removeAttribute("open");
};

// Every kernel screen loads lazily (app/screens.ts). In the whole run, with coverage and every
// worker busy, a screen's first import can take past the default second: give findBy and
// waitFor three.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => {
  cleanup();
});
