# Public-repo sanitization checklist

**Do not publish from an agent.** Public export happens only after private `main` merge, from a git archive of that SHA.

Use this list before any public copy of the tree is created. The private `LICENSE` is all-rights-reserved until the export writes Apache-2.0.

## License and provenance

- [ ] Public `LICENSE` is **Apache-2.0**.
- [ ] `NOTICE` is present.
- [ ] [BUILD_PROVENANCE.md](BUILD_PROVENANCE.md) and [PROVENANCE.md](PROVENANCE.md) are included and do not claim the whole platform was built this week.
- [ ] Root `README.md` links the live demo, honesty, architecture, and provenance. It does **not** claim AgentCore.

## Secrets and identity

- [ ] No `.env`, `credentials`, `*.pem`, or AWS access keys. `.env.example` and `infra/aws/env.example` stay names-only.
- [ ] Operator IAM, Builder ID, `docs/submissions-aws/iam/`, `LIVE_BEDROCK_*` operator notes, and `LIVE_RECORDING.md` are omitted.
- [ ] No AWS account ids, IAM ARNs, operator profile names, or Builder ID email.
- [ ] No LiteAPI/Prioticket credentials.
- [ ] No hosted backend origin IP, SSH keys, or local filesystem paths (`/Users/...`).
- [ ] `.claude/` stays out of the public commit.
- [ ] Private git history is not copied; export is a fresh tree from `git archive`.

## Product honesty

- [ ] README states hosted staging is process-local; local default is fake mode.
- [ ] Flight/hotel = sandbox research; parking Curated offers = simulated; A4 = simulated reservation action / simulated receipt.
- [ ] `/v1/aws/**` is not documented as the browser UI path.
- [ ] Google/Gemini adapter is not claimed as part of this Devpost.
- [ ] No production AgentCore.

## Git hygiene

- [ ] Export from `docs/submissions-aws/prepare_public_export.py` or an equivalent archive, not by flipping the private remote to public.
- [ ] `make secrets` passes on the export tree.
- [ ] No customer PII, real card data, or non-fixture addresses.

## Submission assets

- [ ] Architecture SVG + mermaid source
- [ ] ≤5-minute demo video (Script A) without AWS console or credentials
- [ ] Setup instructions that run **without** cloud credentials (`ITAA_AWS_MODEL_MODE=fake`)
- [ ] Honesty / simulation statement
- [ ] Final demo script
