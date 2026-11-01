# Security policy

Patchground builds and runs challenge code in Docker. Weaknesses in that boundary matter to us.
Examples include escaping the sandbox, reaching the network during checks, running pack content
without consent, leaking hidden checks or reference solutions, and modifying a learner's Git state.

## Reporting a vulnerability

Please report privately through
[GitHub private vulnerability reporting](https://github.com/franndeli/patchground/security/advisories/new).
Do not open a public issue. Include the Patchground version (`pgnd --version`), your platform and
container engine, and the smallest reproduction you can share.

We aim to acknowledge reports within a week. Please allow us to release a fix before you disclose
the issue publicly.

## Supported versions

Patchground is pre-1.0. Only the latest release receives security fixes.
