# Public-repo sanitization checklist

This public export is licensed under **Apache License 2.0**. The private product repository license is unchanged.

Use this list before any public GitHub push. This file records the export-tree status, not an instruction to publish.

## License and provenance

- [x] Product Owner chose **Apache-2.0**. See root `LICENSE` and `NOTICE`.
- [x] [PROVENANCE.md](PROVENANCE.md) distinguishes pre-existing platform work from competition-period AWS work.
- [x] Root `README.md` does **not** claim AgentCore, a public live URL, or that the judge video is live unless recorded.

## Secrets and identity

- [x] No `.env`, `credentials`, `*.pem`, or AWS access keys. `.env.example` and `infra/aws/env.example` stay names-only.
- [x] Operator IAM/account Bedrock setup material, Builder ID details, and `iam/*.json` are excluded.
- [x] No AWS account ids, IAM ARNs, or IAM user ids in README/Devpost/demo script.
- [x] Negative test assertions that previously used a real account number now use the synthetic AWS example account `123456789012`.
- [x] `.claude/` and other local agent config stay out of this tree.

## Product honesty

- [x] Public README states fake-mode demo, simulated suppliers/payment, process-local sessions.
- [x] `/v1/aws/**` is not documented as the browser UI path.
- [x] Google/Gemini adapter is not claimed as part of this Devpost.
- [x] No production AgentCore, public live-demo URL, or “judge video is live Bedrock” unless actually recorded.

## Git hygiene

- [x] Export from a dedicated public-export sandbox, not by flipping the private remote to public.
- [ ] `git log` / `git rev-list --all` on the future public repo (this sandbox has no `.git` history by design).
- [x] `make secrets` on this export tree (passed during export finalization).
- [x] No customer PII, real card data, or non-fixture addresses.

## Submission assets

- [x] Architecture SVG + mermaid source
- [ ] ≤5-minute demo video (recording still gated)
- [x] Setup instructions that run **without** cloud credentials (`ITAA_AWS_MODEL_MODE=fake`)
