// @ts-check

import { createRequire } from "node:module";

// MegaLinter runs its bundled ESLint v10 outside this repository. Native ESM
// resolution does not honor MegaLinter's NODE_PATH, while CommonJS require does.
// createRequire therefore keeps the flat config compatible with both the
// project-local ESLint installation and MegaLinter's bundled dependencies.
const require = createRequire(import.meta.url);
const eslint = require("@eslint/js");
const globals = require("globals");
const tseslint = require("typescript-eslint");

export default tseslint.config(
  {
    ignores: [
      ".direnv/*",
      ".tox/*",
      ".venv/*",
      ".vscode/*",
      "node_modules/*",
      "coverage/*",
      "reports/*",
      "api/_lib/*",
      "**/dist/*",
      "**/tests/*",
      "tsconfig.json",
    ],
  },
  eslint.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["scripts/**/*.mjs", "*.mjs"],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
);
