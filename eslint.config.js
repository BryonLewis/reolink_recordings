import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: ["node_modules/"],
  },
  js.configs.recommended,
  {
    files: ["custom_components/reolink_recordings/frontend/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        customElements: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
];
