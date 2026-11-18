/**
 * One React.lazy per loader, made once, so a page or part never loads twice
 * and keeps its state between renders.
 */
import { lazy as reactLazy, type ComponentType, type LazyExoticComponent } from "react";

import type { Lazy } from "../slots/types";

const made = new WeakMap<Lazy, LazyExoticComponent<ComponentType>>();

export function lazyPart(load: Lazy): LazyExoticComponent<ComponentType> {
  let part = made.get(load);
  if (!part) {
    part = reactLazy(load);
    made.set(load, part);
  }
  return part;
}
