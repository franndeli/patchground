# Examples

Each folder here is a complete, hand-made challenge in the v0.1 format
(`docs/contracts/challenge-format.md`): a manifest, a ticket, a starting workspace, an image
definition, visible and hidden checks, and a reference patch. They are small on purpose — they show
authors what a good challenge looks like and give Patchground a known-good input for its own tests.

Every example must pass `pgnd validate examples/<id>`: the manifest is valid, the image builds, the
starting workspace fails at least one hidden check, and the reference patch makes every check pass.
A change that breaks validation of an example is a regression.
