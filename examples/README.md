# Examples

Each folder is a complete challenge in the [v0.1 format](../docs/contracts/challenge-format.md):
a manifest, a ticket, a starting workspace, an image definition, visible and hidden checks, and a
reference patch. The manifest records whether it is handmade or generated. Generated challenges name
the observed model and prompt version; difficulty and timeboxes are author estimates, not human ratings.

Every example must pass all six steps of `pgnd validate examples/<id>` in Docker: manifest, build,
broken-state failure, reference success, repeatability, and supported editable-test tampering checks.
A `not_run` step is not passing evidence. Never run challenge code or checks on the host.

The CLI wheel and website catalog derive their built-in challenges from these folders. Repository
tests verify discovery and packaged resources; website tests compare the generated cards and JSON
with the manifests. No hand-edited registry entry is needed. Adding source content does not deploy
the website or update a previously published PyPI version.
