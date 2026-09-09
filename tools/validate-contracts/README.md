# tools/validate-contracts

Canonical contract validation, generation, and non-mutating drift detection for `packages/contracts`.

JSON Schema 2020-12 files are authoritative. This tool:

1. Checks `registry.json` against the committed schema files.
2. Validates schemas against the bundled Draft 2020-12 meta-schema without network access.
3. Validates positive and negative fixtures, including cross-field invariants.
4. Regenerates Python and TypeScript representations into a temporary directory and fails if committed output differs.

Make resolves `uv`, `pnpm`, and `node` to absolute paths and passes `--node-bin` / `--pnpm-bin` into this tool so generation does not depend on the caller PATH. Direct invocation searches `ITAA_NODE_BIN` / `ITAA_PNPM_BIN`, then PATH, then `/usr/local/bin`, `/opt/homebrew/bin`, and `$HOME/.local/bin`. Missing tools fail with a remediation message instead of a traceback.

```bash
make generate-contracts   # rewrite packages/contracts/generated
make validate-contracts   # schema, registry, fixtures, invariants, drift
```
