// ESLint for this site's web app, as MechFrame's own (SPEC.md section 16: zero warnings).
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

const COLOUR = String.raw`(?:^|[\s(,:])#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![\w-])|\b(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch|color)\(`;

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/coverage/**",
      "test-results/**",
      "playwright-report/**",
      // Generated from the kernel's openapi.json, in MechFrame.
      "src/kernel/src/api/schema.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/consistent-type-imports": "error",
      // No colour written in code: a page takes its colours from the theme's tokens
      // (var(--mf-color-*), src/theme/tokens.css).
      "no-restricted-syntax": [
        "error",
        {
          selector: `Literal[value=/${COLOUR}/]`,
          message: "A colour comes from the theme: use a var(--mf-color-*) token.",
        },
        {
          selector: `TemplateElement[value.raw=/${COLOUR}/]`,
          message: "A colour comes from the theme: use a var(--mf-color-*) token.",
        },
      ],
    },
  },
  {
    // A test may compare a colour as the browser computes it.
    files: ["**/*.test.{ts,tsx}", "e2e/**"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    files: ["eslint.config.js"],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: { ...globals.node } },
  },
);
