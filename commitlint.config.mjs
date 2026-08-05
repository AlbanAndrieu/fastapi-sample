import config from "@commitlint/config-conventional";
import createPreset from "conventional-changelog-conventionalcommits";

async function createEmojiParser() {
  const emojiRegexPart = Object.values(config.prompt.questions.type.enum)
    .map((value) => value.emoji.trim())
    .join("|");

  const parserOpts = {
    breakingHeaderPattern: new RegExp(
      `^(?:${emojiRegexPart})\\s+(\\w*)(?:\\((.*)\\))?!:\\s+(.*)$`,
    ),
    headerPattern: new RegExp(
      `^(?:${emojiRegexPart})\\s+(\\w*)(?:\\((.*)\\))?!?:\\s+(.*)$`,
    ),
  };

  const preset = await createPreset();

  return {
    ...preset,
    conventionalChangelog: {
      ...preset.conventionalChangelog,
      parserOpts,
    },
    parserOpts: {
      ...preset.parserOpts,
      ...parserOpts,
    },
    recommendedBumpOpts: {
      ...preset.recommendedBumpOpts,
      parserOpts,
    },
  };
}

const emojiParser = await createEmojiParser();

export default {
  extends: ["@commitlint/config-conventional"],
  parserPreset: {
    emojiParser,
    parserOpts: {
      issuePrefixes: ["ANDR-", "TEST-", "DSC-", "NABLA-", "AA-"],
    },
  },
  rules: {
    "body-max-line-length": [2, "always", 100],
    "body-leading-blank": [1, "always"],
    "footer-leading-blank": [1, "always"],
    "header-max-length": [2, "always", 80],
    "scope-case": [2, "always", "lower-case"],
    "subject-case": [
      2,
      "never",
      ["sentence-case", "start-case", "pascal-case", "upper-case"],
    ],
    "subject-empty": [2, "never"],
    "subject-full-stop": [2, "never", "."],
    "type-case": [2, "always", "lower-case"],
    "type-empty": [2, "never"],
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
};
