# tools/redact-check

Workspace secret and credential-pattern scan used by local quality commands and CI.

This is a foundation check, not a complete DLP program. It must fail on private keys and common cloud/token patterns. `.env.example` local defaults are allowlisted.
