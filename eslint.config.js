// ESLint for every web workspace (SPEC.md section 16: zero warnings).
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/coverage/**",
      ".venv/**",
      "modules/_template/**",
      "templates/**",
      // Generated from kernel/openapi.json (npm run api:types); api:check holds it current.
      "kernel/web/src/api/schema.ts",
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
      // No colour written in code: a part takes its colours from the theme's
      // tokens (SPEC.md section 16, themes/README.md). tests/test_themes.py
      // checks the CSS the same way. A hex of 3, 4, 6 or 8 digits anywhere in
      // a string or a template (a shadow's "0 0 2px #123456" too), or a colour
      // function, color() among them (cubic and CodeRabbit on #80).
      "no-restricted-syntax": [
        "error",
        {
          selector: String.raw`Literal[value=/(?:^|[\s(,:])#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![\w-])|\b(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch|color)\(/]`,
          message: "A colour comes from the theme: use a var(--mf-color-*) token.",
        },
        {
          selector: String.raw`TemplateElement[value.raw=/(?:^|[\s(,:])#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![\w-])|\b(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch|color)\(/]`,
          message: "A colour comes from the theme: use a var(--mf-color-*) token.",
        },
      ],
    },
  },
  {
    // A test may compare a colour as the browser computes it.
    files: ["**/*.test.{ts,tsx}", "kernel/tests/e2e/**"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    files: ["eslint.config.js"],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: { ...globals.node } },
  },
);
