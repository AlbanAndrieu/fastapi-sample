// @ts-check
import { createConfigForNuxt } from '@nuxt/eslint-config/flat';

// Run `npx @eslint/config-inspector` to inspect the resolved config interactively
export default createConfigForNuxt({
  features: {
    // Rules for module authors
    tooling: true,
    // Rules for formatting
    stylistic: true,
  },
})
  .append({
    // Enums has to be ignored, since it breaks eslint on incorrect @stylistic/brace-style
    ignores: ['**/storybook-static', '**/.storybook'],
  })
  .overrideRules({
    '@stylistic/eol-last': 'off',
    '@stylistic/js/indent': ['error', 2],
    'vue/multi-word-component-names': 'off',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    '@stylistic/semi': ['error', 'always'],
    '@stylistic/brace-style': ['error', '1tbs'],
  });
