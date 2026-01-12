import config from "@commitlint/config-conventional";
import type { ParserPreset, UserConfig } from "@commitlint/types";
import createPreset from "conventional-changelog-conventionalcommits";
import { merge } from "lodash-es";

// A helper function to create the custom emoji parser preset.
async function createEmojiParser(): Promise<ParserPreset> {
	// Generates the regex from the emojis defined in the conventional config.
	const emojiRegexPart = Object.values(config.prompt.questions.type.enum)
		.map((value) => value.emoji.trim())
		.join("|");

	const parserOpts = {
		// This regular expression validates commit headers with an emoji.
		breakingHeaderPattern: new RegExp(
			`^(?:${emojiRegexPart})\\s+(\\w*)(?:\\((.*)\\))?!:\\s+(.*)$`,
		),
		headerPattern: new RegExp(
			`^(?:${emojiRegexPart})\\s+(\\w*)(?:\\((.*)\\))?!?:\\s+(.*)$`,
		),
	};

	const emojiParser = merge({}, await createPreset(), {
		conventionalChangelog: { parserOpts },
		parserOpts,
		recommendedBumpOpts: { parserOpts },
	});

	return emojiParser;
}

const emojiParser = await createEmojiParser();

export default {
	extends: ["@commitlint/config-conventional"],
	parserPreset: {
		emojiParser,
		parserOpts: {
			// these are samples, add possible prefixes based on your project requirement
			issuePrefixes: ["ANDR-", "TEST-", "DSC-", "ABC-", "CO-"],
		},
	},
	rules: {
		//  Wrap the body at 72 characters.
		"body-max-line-length": [2, 'always', 72],
		//  Body is added by leaving a blank line after the subject line.
		"body-leading-blank": [1, "always"],
		// Ensure a blank line precedes the footer.
		"footer-leading-blank": [1, "always"],
		// Subject/Description Rules:
        // Short and Summarized: Try to fit the subject line inside 72 characters.
		"header-max-length": [2, "always", 72],
		// Enforce that if a scope is used, it is in lower-case.
		"scope-case": [2, "always", "lower-case"],
		// Capitalize the description: Start subject line with a capital letter.
        // 'sentence-case' helps with generating changelogs.
		"subject-case": [
			2,
			"always",
			"sentence-case",
		],
		"subject-empty": [2, "never"],
		 // Avoid trailing period.
		"subject-full-stop": [2, "never", "."],
		"type-case": [2, "always", "lower-case"],
		// Format: <type>([optional scope]): <description> - enforced by most rules below.
        // Enforce that the type is not empty.
		"type-empty": [2, "never"],
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
	prompt: {
		questions: {
			type: {
				enum: {
					// Customize emojis and add the extra space for better alignment.
					build: { emoji: "🛠️ " },
					chore: { emoji: "♻️ " },
					ci: { emoji: "⚙️ " },
					revert: { emoji: "🗑️ " },
				},
				// This setting includes the emoji in the final commit header.
				headerWithEmoji: true,
			},
		},
	},
} satisfies UserConfig;
