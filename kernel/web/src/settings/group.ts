/**
 * The settings forms drawn on one page, for that page's one Save and its
 * unsaved-changes question (K4.8; CodeRabbit on #87): the Site tab provides
 * it around the modules' `admin.settings.section` parts, and each
 * `useSettings` form inside joins it while it's drawn, saying whether it
 * has changes and how to save them.
 */
import { createContext } from "react";

import type { SaveOutcome } from "./useSettings";

export type GroupMember = { dirty: boolean; save: () => Promise<SaveOutcome> };

export type SettingsGroup = {
  join: (key: symbol, member: GroupMember) => void;
  leave: (key: symbol) => void;
};

export const SettingsGroupContext = createContext<SettingsGroup | null>(null);
