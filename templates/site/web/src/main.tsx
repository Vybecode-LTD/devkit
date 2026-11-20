// This site's web app: the theme, then the kernel's shell with the site's modules and its own pages.
import "./theme/tokens.css";

import { mountApp } from "@/kernel";

import { modules } from "./modules";
import { site } from "./site/site";

void mountApp({ modules, site });
