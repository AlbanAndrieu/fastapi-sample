// @ts-check

import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import globals from "globals";

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
