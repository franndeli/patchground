# Publishing a release

Maintainer runbook. Every step that makes something public requires the owner's explicit approval
at the time it happens; this document describes the steps, it does not authorize them.

## One-time setup (owner, in web dashboards)

1. **GitHub environments.** Repository → Settings → Environments: create `release` and `pypi`, each
   with *Required reviewers* set to the owner and deployment limited to tags matching `v*`.
   Without a required reviewer, a pushed tag would publish without a second confirmation.
2. **PyPI trusted publisher.** On pypi.org → Account → Publishing → *Add a pending publisher*:
   project `patchground`, owner `franndeli`, repository `patchground`, workflow `release.yml`,
   environment `pypi`. No API token is created or stored.
3. **Cloudflare (Workers static assets).** Workers & Pages → Create → import the GitHub repository:
   - Worker name `patchground` (must equal `name` in `wrangler.jsonc`); production branch `main`;
   - build command `npm --prefix web run build`; deploy command `npx wrangler deploy` (default);
   - build variable `NODE_VERSION=24`.
   `wrangler.jsonc` serves `web/dist` as static assets with no Worker script. The build has no
   dependencies to install and refuses to publish a stale catalog. Then add the custom domain
   `patchground.dev` under the Worker's *Settings → Domains & Routes*; Cloudflare creates the DNS
   record in the existing zone. Non-production branch builds can be disabled in the build settings.

## Release checklist

1. Human acceptance gate passed and recorded in `docs/evaluations/human-trial-findings.md`.
2. `pyproject.toml` version and the matching `CHANGELOG.md` section are committed on `main`, and CI,
   the validation Action smoke test and the secret scan are green for that commit.
3. Tag and push (owner approval required): `git tag v0.1.0 && git push origin v0.1.0`.
4. The `release` workflow builds and verifies the wheel and sdist, then waits. Approve the
   `release` environment to create the GitHub release with checksums, then approve `pypi` to upload.
5. After PyPI shows the version: update install instructions (README, `docs/first-session.md`,
   `web/public/index.html` and the website's "install from a checkout" test) to
   `uv tool install patchground`, regenerate and test the site, and push. Cloudflare Pages deploys
   `main` automatically.

## If something goes wrong

- A failed `build` job publishes nothing; fix, delete the tag locally and remotely, re-tag.
- PyPI versions are immutable: a broken upload is yanked on pypi.org and fixed with a new patch version.
- A GitHub release can be edited or deleted; the tag should then be deleted too.
