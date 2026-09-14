# COMP-AWS-06 public-export preparation (do not publish from an agent)

Product Owner gated. An agent must not `git push` to a public remote, open a public GitHub repo, or submit Devpost until private `main` has the final SHA and this sandbox is reviewed.

Order after private merge:

1. `git archive` the exact private `main` SHA
2. Run the sanitizer below (Apache-2.0 `LICENSE` + `NOTICE`; strip operator files)
3. Update [BUILD_PROVENANCE.md](BUILD_PROVENANCE.md) with that SHA
4. Push the **public** repository as a fresh history
5. Verify a clean clone + `make setup` in fake mode
6. Confirm https://bookingdemo.reservedge.com still matches that SHA’s behaviour
7. Submit Devpost

## Local sandbox

From the repository root:

```bash
uv run python docs/submissions-aws/prepare_public_export.py
```

Writes `artifacts/comp-aws-06-sandbox/` (gitignored). Omits `.git`, secrets, `.claude/`, operator Bedrock/IAM files, Builder ID, and `LIVE_RECORDING.md`. Replaces private `LICENSE` with Apache-2.0 from `docs/submissions-aws/public-export/LICENSE.Apache-2.0` and copies root `NOTICE`.

Then on the sandbox:

- [ ] Run [PUBLIC_REPO_SANITIZATION.md](PUBLIC_REPO_SANITIZATION.md).
- [ ] `make secrets` if toolchains are installed.
- [ ] Confirm README does not claim AgentCore and does name the live demo as process-local staging.
- [ ] Do not add a public remote from this sandbox until Product Owner authorizes publish.

## Must be present in the public tree

- All source required to run locally
- `.env.example` (never `.env`)
- Setup instructions
- Apache-2.0 `LICENSE` and `NOTICE`
- `docs/demo-aws/architecture.mmd` and `architecture.svg`
- Root `README.md`
- Provenance and honesty
- Final demo script
