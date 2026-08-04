// @ts-check

import eslint from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

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
