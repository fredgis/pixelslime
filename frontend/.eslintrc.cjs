/**
 * ESLint configuration for the PIXELSLIME frontend.
 *
 * The `lint` script and the plugins below were declared in package.json from the
 * start, but no config file was ever committed, so `npm run lint` failed with
 * "couldn't find a configuration file" on every run and the Frontend CI job never
 * actually linted anything. This file is that missing piece.
 *
 * eslintrc format rather than flat config, because the pinned ESLint is 8.57 and
 * flat config is not its default there. Kept non-type-aware on purpose: type errors
 * are already caught by `tsc --noEmit` in the same CI job, and adding
 * `parserOptions.project` would make lint several times slower to re-report them.
 */
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['@typescript-eslint', 'react-refresh'],
  rules: {
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

    // AGENTS.md states the rule plainly: "No `any`." The recommended set only warns,
    // which in practice means it accumulates. An unused variable is likewise a real
    // signal here rather than noise - except for the deliberate `_`-prefixed throwaway.
    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/no-unused-vars': [
      'error',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
    ],
  },
};
