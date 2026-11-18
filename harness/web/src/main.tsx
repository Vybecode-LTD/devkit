// The harness's web app: the kernel's shell with every module built in this
// repo (modules/<id>/web/module.web.ts). The scaffolds still waiting to be
// built (modules/_<id>) and the template are left out.
import { mountApp, type ModuleDefinition } from "@/kernel";

const bindings = import.meta.glob<{ default: ModuleDefinition }>(
  ["../../../modules/*/web/module.web.ts", "!../../../modules/_*/**"],
  { eager: true },
);

mountApp({ modules: Object.values(bindings).map((binding) => binding.default) });
