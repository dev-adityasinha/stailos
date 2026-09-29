import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // This app's entire client-side data-fetching architecture is
      // `useEffect(() => { load(); }, [deps])` calling an async function
      // that setStates after awaiting — the standard, correct-at-runtime
      // pattern used consistently across every dashboard page. The React
      // Compiler's new purity rule flags it everywhere (no bug, just a
      // stricter idiom than this codebase was written against); rewriting
      // ~20 working, tested pages to a different fetching pattern is out of
      // proportion to the rule's actual payoff here. Kept as a warning
      // (visible, not silenced) rather than a hard CI-blocking error.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
