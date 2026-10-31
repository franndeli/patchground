"""Typed pack identity, review and preparation contracts; no execution or storage."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from patchground.spec.models import SemVer, Slug


class PackError(Exception):
    """An operation cannot safely resolve or manage a pack."""


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceSnapshot(Model):
    path: Path
    source: str
    source_kind: Literal["https", "local"]
    commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class PackIdentity(Model):
    name: Slug
    version: SemVer
    source: str
    source_kind: Literal["https", "local"]
    commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust: Literal["unofficial"] = "unofficial"


class PackInfo(Model):
    pack: PackIdentity
    path: Path
    ref: str
    consented: bool
    active: bool = True


class PackProblem(Model):
    name: str
    reason: str


class PackListing(Model):
    packs: tuple[PackInfo, ...]
    invalid: tuple[PackProblem, ...] = ()


class ExecutionRecipe(Model):
    challenge_id: Slug
    dockerfile_path: str
    dockerfile: str
    services: tuple[str, ...]
    command: str


class PackReview(Model):
    pack: PackIdentity
    recipes: tuple[ExecutionRecipe, ...]
    previous_commit: str | None = None
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()


class ConsentRequired(PackError):
    def __init__(self, review: PackReview) -> None:
        super().__init__("explicit consent is required for this pack revision")
        self.review = review


class PackUpdateResult(Model):
    current: PackInfo
    previous_commit: str
    changed: bool


class PackRemoval(Model):
    name: str
    removed_versions: int


class ResolvedChallenge(Model):
    path: Path
    pack: PackIdentity | None = None


class PreparedChallenge(Model):
    path: Path
    source_path: Path
    pack: PackIdentity | None = None
    input_roots: tuple[Path, ...] = ()
