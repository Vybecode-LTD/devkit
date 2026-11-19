// The harness's web app: the kernel's shell with every module built in this
// repo (modules/<id>/web/module.web.ts). The scaffolds still waiting to be
// built (modules/_<id>) and the template are left out.
// Both themes, so a page can be checked in each (<html data-theme="...">); a
// site imports its own one.
import "../../../themes/machined-light/tokens.css";
import "../../../themes/vibrant-mindz/tokens.css";

import { mountApp, type ModuleDefinition } from "@/kernel";

const bindings = import.meta.glob<{ default: ModuleDefinition }>(
  ["../../../modules/*/web/module.web.ts", "!../../../modules/_*/**"],
  { eager: true },
);

void mountApp({ modules: Object.values(bindings).map((binding) => binding.default) });
