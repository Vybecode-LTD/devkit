import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
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

afterEach(() => {
  cleanup();
});
