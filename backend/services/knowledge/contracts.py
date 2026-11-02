"""Validated proposals shared by HTTP, compiler and publisher."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Block(Contract):
    block_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=12000)
    span_ids: list[str] = Field(min_length=1, max_length=50)
    epistemic_status: Literal["reported", "inference", "uncertain"] = "reported"


class PageOperation(Contract):
    page_id: str = Field(pattern=r"^kp-[a-f0-9]{32}$")
    base_revision: int = Field(ge=0)
    type: Literal["source", "concept", "entity", "synthesis"]
    title: str = Field(min_length=1, max_length=240)
    blocks: list[Block] = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    superseded_by: str = Field(default="", pattern=r"^(kp-[a-f0-9]{32})?$")


class LinkOperation(Contract):
    from_page_id: str
    to_page_id: str
    relation: Literal["MENTIONS", "SUPPORTS", "CONTRADICTS", "DERIVED_FROM", "RELATED_TO", "SUPERSEDES"]
    rationale: str = Field(min_length=1, max_length=1000)


class Proposal(Contract):
    schema_version: Literal["kb-change-v1"] = "kb-change-v1"
    space_epoch: int = Field(ge=0)
    policy_revision: Literal["kb-policy-v1"] = "kb-policy-v1"
    source_version_ids: list[str] = Field(min_length=1, max_length=20)
    pages: list[PageOperation] = Field(min_length=1, max_length=30)
    links: list[LinkOperation] = Field(default_factory=list, max_length=100)
    link_targets: dict[str, int] = Field(default_factory=dict, max_length=100)
    extraction_mode: Literal["extractive-v1", "reviewed-proposal-v1"]


class MaintenanceRequest(Contract):
    action: Literal["rename", "merge", "relate", "edit"]
    page_id: str = Field(pattern=r"^kp-[a-f0-9]{32}$")
    base_revision: int = Field(ge=1)
    title: str = Field(default="", max_length=240)
    target_page_id: str = Field(default="", pattern=r"^(kp-[a-f0-9]{32})?$")
    target_revision: int = Field(default=0, ge=0)
    relation: Literal["MENTIONS", "SUPPORTS", "CONTRADICTS", "DERIVED_FROM", "RELATED_TO", "SUPERSEDES"] = "RELATED_TO"
    reason: str = Field(min_length=1, max_length=1000)
    blocks: list[Block] = Field(default_factory=list, max_length=100)
