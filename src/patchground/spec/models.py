"""Pydantic v2 models for ``challenge.yaml`` and ``pack.yaml`` v0.1.

These models are the executable form of ``patchground-contract-challenge-format``. If the contract
and the models disagree, the contract wins and the models are fixed.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    WithJsonSchema,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

SPEC_VERSION = "0.1"

EXTENSION_PREFIX = "x-"
"""Keys starting with this prefix are accepted and ignored at every mapping level."""

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
# Semantic Versioning 2.0.0, the regex recommended on semver.org.
SEMVER_PATTERN = (
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

_SLUG_RE = re.compile(SLUG_PATTERN)
_SEMVER_RE = re.compile(SEMVER_PATTERN)


# --------------------------------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------------------------------


class ChallengeType(StrEnum):
    """Kind of challenge."""

    DEBUG = "debug"
    FEATURE = "feature"
    REVIEW = "review"
    REFACTOR = "refactor"


class Difficulty(StrEnum):
    """Intended difficulty."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class AIPolicy(StrEnum):
    """Whether the user may use AI assistance."""

    ALLOWED = "allowed"
    FORBIDDEN = "forbidden"


class Provenance(StrEnum):
    """How the challenge was authored."""

    HANDMADE = "handmade"
    GENERATED = "generated"


RESERVED_CHALLENGE_TYPES = frozenset({"incident", "ai-validation", "design"})
RESERVED_AI_POLICIES = frozenset({"trap"})


def _reject_reserved(reserved: frozenset[str]) -> Any:
    def check(value: Any) -> Any:
        if isinstance(value, str) and value in reserved:
            raise PydanticCustomError(
                "reserved_value",
                "'{value}' is reserved and not part of format v0.1",
                {"value": value},
            )
        return value

    return BeforeValidator(check)


def _check_spec_version(value: Any) -> Any:
    if isinstance(value, float | int) and not isinstance(value, bool) and str(value) == "0.1":
        raise PydanticCustomError(
            "spec_version_not_string",
            'spec_version must be the string "0.1"; quote it: spec_version: "0.1"',
        )
    return value


SpecVersion = Annotated[Literal["0.1"], BeforeValidator(_check_spec_version)]


# --------------------------------------------------------------------------------------------------
# Scalar types
# --------------------------------------------------------------------------------------------------


def _check_not_blank(value: str) -> str:
    if not value.strip():
        raise PydanticCustomError("blank_string", "must not be blank")
    return value


def _check_semver(value: str) -> str:
    if not _SEMVER_RE.match(value):
        raise PydanticCustomError(
            "semver", "'{value}' is not a semantic version (e.g. 1.0.0)", {"value": value}
        )
    return value


def _check_slug(value: str) -> str:
    if not _SLUG_RE.match(value):
        raise PydanticCustomError(
            "slug",
            "'{value}' is not a kebab-case slug (lowercase letters, digits and single dashes)",
            {"value": value},
        )
    return value


def relative_path_problem(value: str, container: str = "challenge folder") -> str | None:
    """Return why ``value`` is not an acceptable manifest path, or ``None`` if it is.

    Manifest paths are relative POSIX strings that stay inside ``container`` (the challenge folder
    by default; the workspace for ``expected_paths``) lexically. A trailing ``/`` is allowed.
    Symlinks are checked against the filesystem by the loader, not here.
    """
    if not value or not value.strip():
        return "path must not be empty"
    if "\\" in value:
        return "path must use '/' as separator"
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return f"path must be relative to the {container}"
    depth = 0
    for part in value.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                return f"path must stay inside the {container}"
        else:
            depth += 1
    if depth == 0:
        return f"path must point inside the {container}, not at the {container} itself"
    return None


def _check_relative_path(value: str) -> str:
    problem = relative_path_problem(value)
    if problem is not None:
        raise PydanticCustomError("relative_path", problem)
    return value


def _check_workspace_path(value: str) -> str:
    problem = relative_path_problem(value, "workspace")
    if problem is not None:
        raise PydanticCustomError("relative_path", problem)
    return value


# Custom validators carry the readable messages; WithJsonSchema keeps the exported schema precise.
NonEmptyStr = Annotated[
    str,
    AfterValidator(_check_not_blank),
    WithJsonSchema({"type": "string", "minLength": 1}),
]
Slug = Annotated[
    str,
    AfterValidator(_check_slug),
    WithJsonSchema({"type": "string", "pattern": SLUG_PATTERN}),
]
SemVer = Annotated[
    str,
    AfterValidator(_check_semver),
    WithJsonSchema({"type": "string", "pattern": SEMVER_PATTERN}),
]
RelPath = Annotated[
    str,
    AfterValidator(_check_relative_path),
    WithJsonSchema(
        {
            "type": "string",
            "minLength": 1,
            "description": "Relative POSIX path inside the challenge folder "
            "(no absolute paths, must not escape the folder).",
        }
    ),
]

WorkspacePath = Annotated[
    str,
    AfterValidator(_check_workspace_path),
    WithJsonSchema(
        {
            "type": "string",
            "minLength": 1,
            "description": "Relative POSIX path inside the workspace (no absolute paths, must not "
            "escape the workspace; a trailing '/' marks a directory). Need not exist.",
        }
    ),
]

# The models validate the str/int types from YAML without lax coercion of, e.g., "45" -> 45.
StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]


# --------------------------------------------------------------------------------------------------
# Base model: unknown keys rejected, ``x-`` keys accepted and ignored
# --------------------------------------------------------------------------------------------------


def _extension_schema(schema: dict[str, Any]) -> None:
    schema["additionalProperties"] = False
    schema["patternProperties"] = {"^x-": {}}


class ManifestModel(BaseModel):
    """Shared base: rejects unknown keys except x- extensions, which are dropped."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra=_extension_schema,
    )

    @model_validator(mode="before")
    @classmethod
    def _drop_extension_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {
                key: value
                for key, value in data.items()
                if not (isinstance(key, str) and key.startswith(EXTENSION_PREFIX))
            }
        return data


# --------------------------------------------------------------------------------------------------
# challenge.yaml
# --------------------------------------------------------------------------------------------------


class Environment(ManifestModel):
    """Runtime image and test command."""

    dockerfile: RelPath
    services: list[NonEmptyStr] = Field(default_factory=list)
    test_command: NonEmptyStr


class Checks(ManifestModel):
    """Visible checks are copied into the workspace; hidden checks never are."""

    visible: RelPath | None = None
    hidden: RelPath


class Author(ManifestModel):
    """Challenge author."""

    name: NonEmptyStr
    github: NonEmptyStr | None = None


class Debrief(ManifestModel):
    """Optional interviewer prompts and unweighted coaching areas."""

    questions: RelPath | None = None
    focus: list[NonEmptyStr] = Field(default_factory=list)


class GeneratedBy(ManifestModel):
    """Model and prompt version of a generated challenge."""

    model: NonEmptyStr
    prompt_version: NonEmptyStr


def _single_error(title: str, loc: tuple[str | int, ...], message: str, value: Any) -> ValueError:
    """Build a ValidationError that pins ``message`` to ``loc`` (relative to the current model)."""
    return ValidationError.from_exception_data(
        title,
        [InitErrorDetails(type=PydanticCustomError("manifest", message), loc=loc, input=value)],
    )


def _challenge_schema_extra(schema: dict[str, Any]) -> None:
    _extension_schema(schema)
    # generated_by is required when provenance is "generated" and forbidden otherwise.
    schema["if"] = {
        "properties": {"provenance": {"const": Provenance.GENERATED.value}},
        "required": ["provenance"],
    }
    schema["then"] = {
        "properties": {"generated_by": {"type": "object"}},
        "required": ["generated_by"],
    }
    schema["else"] = {"properties": {"generated_by": {"type": "null"}}}


class ChallengeManifest(ManifestModel):
    """Manifest of a challenge folder (challenge.yaml, format v0.1)."""

    model_config = ConfigDict(
        title="Patchground challenge.yaml v0.1",
        json_schema_extra=_challenge_schema_extra,
    )

    spec_version: SpecVersion
    id: Slug
    version: SemVer
    title: NonEmptyStr
    type: Annotated[ChallengeType, _reject_reserved(RESERVED_CHALLENGE_TYPES)]
    summary: NonEmptyStr
    languages: Annotated[list[NonEmptyStr], Field(min_length=1)]
    tags: list[NonEmptyStr] = Field(default_factory=list)
    difficulty: Difficulty
    timebox_minutes: StrictPositiveInt
    ai_policy: Annotated[AIPolicy, _reject_reserved(RESERVED_AI_POLICIES)]
    environment: Environment
    checks: Checks
    solution: RelPath
    expected_paths: list[WorkspacePath] = Field(default_factory=list)
    hints: list[NonEmptyStr] = Field(default_factory=list)
    debrief: Debrief | None = None
    author: Author
    content_license: NonEmptyStr = "CC-BY-4.0"
    provenance: Provenance = Provenance.HANDMADE
    generated_by: GeneratedBy | None = None

    @model_validator(mode="after")
    def _check_generated_by(self) -> Self:
        if self.provenance is Provenance.GENERATED and self.generated_by is None:
            raise _single_error(
                type(self).__name__,
                ("provenance",),
                "generated_by (model, prompt_version) is required when provenance is 'generated'",
                self.provenance.value,
            )
        if self.provenance is not Provenance.GENERATED and self.generated_by is not None:
            raise _single_error(
                type(self).__name__,
                ("generated_by",),
                "generated_by is only allowed when provenance is 'generated'",
                None,
            )
        return self


# --------------------------------------------------------------------------------------------------
# pack.yaml
# --------------------------------------------------------------------------------------------------


class PackManifest(ManifestModel):
    """Manifest of a pack folder (pack.yaml, format v0.1)."""

    model_config = ConfigDict(title="Patchground pack.yaml v0.1")

    spec_version: SpecVersion
    name: Slug
    version: SemVer
    description: NonEmptyStr
    challenges: Annotated[list[Slug], Field(json_schema_extra={"uniqueItems": True})]

    @field_validator("challenges")
    @classmethod
    def _unique_challenges(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        for index, name in enumerate(value):
            if name in seen:
                raise _single_error(
                    cls.__name__, (index,), f"challenge '{name}' is listed more than once", name
                )
            seen.add(name)
        return value
