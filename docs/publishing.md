# Publishing a release

Maintainer runbook. Every step that makes something public requires the owner's explicit approval
at the time it happens; this document describes the steps, it does not authorize them.

## Current publication state

Version 0.1.0 is published on PyPI and GitHub. The public site uses Cloudflare Workers static assets,
not a Pages project. Human acceptance is still unverified; see the trial findings and next-session
index. The setup below documents the provider configuration, not work that must be repeated.
Whether Cloudflare's dashboard Git-build integration is enabled has not been verified here. Do not
assume a Git push deploys the website.

## One-time setup (owner, in web dashboards)

1. **GitHub environments.** Repository → Settings → Environments: create `release` and `pypi`, each
   with *Required reviewers* set to the owner and deployment limited to tags matching `v*`.
   Without a required reviewer, a pushed tag would publish without a second confirmation.
2. **PyPI trusted publisher.** On pypi.org → Account → Publishing → *Add a pending publisher*:
   project `patchground`, owner `franndeli`, repository `patchground`, workflow `release.yml`,
   environment `pypi`. No API token is created or stored.
3. **Cloudflare (Workers static assets).** Workers & Pages → Create → import the GitHub repository:
   - Worker name `patchground` (must equal `name` in `wrangler.jsonc`); production branch `main`;
   - build command `npm --prefix web ci && npm --prefix web run build`; deploy command
     `npx wrangler deploy` (default);
   - build variable `NODE_VERSION=24`.
   `wrangler.jsonc` serves `web/dist` as static assets with no Worker script. The build installs
   the site's locked build-time dependencies (Astro, Tailwind, Geist fonts) and renders the catalog
   from `examples/` and `registry/` at build time, so it cannot publish a stale catalog. Then add the custom domain
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
   `web/src/components/Install.astro` and the website's install test in `web/scripts/site.test.mjs`)
   to `uv tool install patchground`, run `npm --prefix web test`, and push. Website deployment is a
   separate operation described below; a successful push is not deployment proof.

## Deploy the website after approval

From the intended clean source revision:

```sh
npm --prefix web ci
npm --prefix web run check
npm --prefix web test
npx wrangler deploy
```

The tests build `web/dist` before checking it. Wrangler uses the root `wrangler.jsonc` and the
existing Cloudflare login. Do not print account credentials or copy tokens into files. Confirm the
reported Worker is `patchground` and retain its deployment version ID with the source commit.

Fetch `https://patchground.dev/` and `https://patchground.dev/catalog.json` after deployment. Use a
normal browser if an automated client receives a bot-policy error. Check the actual changed content
and its asset links, not just HTTP 200 or the CLI's upload success. For the guide card, confirm its
skill URL resolves and that copying the visible prompt works. A failed public check is an unresolved
deployment, not permission to alter DNS or disable security controls. Dashboard automation and DNS
changes need their own explicit approval.

## If something goes wrong

- A failed `build` job publishes nothing; fix, delete the tag locally and remotely, re-tag.
- PyPI versions are immutable: a broken upload is yanked on pypi.org and fixed with a new patch version.
- A GitHub release can be edited or deleted; the tag should then be deleted too.
