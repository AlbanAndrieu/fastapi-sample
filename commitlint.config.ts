import config from "commitlint-config-gitmoji";
import type { ParserPreset, UserConfig } from "@commitlint/types";
import createPreset from "conventional-changelog-conventionalcommits";
import { merge } from "lodash-es";

export default {
	extends: ["./node_modules/commitlint-config-gitmoji"],
	parserPreset: {
		parserOpts: {
			// these are samples, add possible prefixes based on your project requirement
			issuePrefixes: ["ANDR-", "TEST-", "DSC-", "NABLA-", "JM-"],
		},
	},
	rules: {
		//  Wrap the body at 100 characters.
		"body-max-line-length": [2, 'always', 100],
		//  Body is added by leaving a blank line after the subject line.
		"body-leading-blank": [1, "always"],
		// Ensure a blank line precedes the footer.
		"footer-leading-blank": [1, "always"],
		// Subject/Description Rules:
        // Short and Summarized: Try to fit the subject line inside 100 characters (with emoji).
		"header-max-length": [2, "always", 110],
		// Enforce that if a scope is used, it is in lower-case.
		"scope-case": [2, "always", "lower-case"],
		// Capitalize the description: Start subject line with a capital letter.
        // 'sentence-case' helps with generating changelogs.
		"subject-case": [
			2,
			"never",
			[ "sentence-case", "start-case", "pascal-case", "upper-case" ]
		],
		"subject-empty": [2, "never"],
		 // Avoid trailing period.
		"subject-full-stop": [2, "never", "."],
		"type-case": [2, "always", "lower-case"],
		// Format: <type>([optional scope]): <description> - enforced by most rules below.
        // Enforce that the type is not empty.
		// "type-empty": [2, "never"],
		// Enforce specific commit types. Add/remove types based on the project.
		"type-enum": [
			2,
			"always",
			[
				"build",
				"chore",
				"ci",
				"docs",
				"feat",
				"feature",
				"fix",
				"perf",
				"refactor",
				"revert",
				"style",
				"test",
			],
		],
	},
} satisfies UserConfig;
