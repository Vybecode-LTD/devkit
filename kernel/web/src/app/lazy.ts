/**
 * One React.lazy per loader, made once, so a page or part never loads twice
 * and keeps its state between renders. A load that fails is forgotten, so
 * the next render makes a new one that asks again: what "Try again" needs
 * after a dropped connection (cubic and CodeRabbit on #79).
 */
import { lazy as reactLazy, type ComponentType, type LazyExoticComponent } from "react";

import type { Lazy } from "../slots/types";

const made = new WeakMap<Lazy, LazyExoticComponent<ComponentType>>();

export function lazyPart(load: Lazy): LazyExoticComponent<ComponentType> {
  let part = made.get(load);
  if (!part) {
    part = reactLazy(() =>
      load().catch((error: unknown) => {
        made.delete(load);
        throw error;
      }),
    );
    made.set(load, part);
  }
  return part;
}
