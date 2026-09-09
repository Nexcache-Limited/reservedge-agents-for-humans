# tests/contract

Canonical contract tests live with the schemas:

- `packages/contracts/tests/test_contracts.py`
- `packages/contracts/tests/test_generation_drift.py`
- `tools/validate-contracts/tests/`

`make validate-contracts` and `make check` run the same checks. This directory is reserved for later cross-package contract scenarios; it does not duplicate schema semantics.
