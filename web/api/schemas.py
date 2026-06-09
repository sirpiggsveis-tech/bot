"""Pydantic request/response models for the ORBAT API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    description: str = ""


class UnitUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    leader_id: int | None = None
    clear_leader: bool = False


class UnitMove(BaseModel):
    new_parent_id: int | None = None


class RankCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    abbreviation: str = ""
    sort_order: int | None = None
    role_id: int | None = None


class RankRole(BaseModel):
    role_id: int | None = None


class PositionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class MemberUpdate(BaseModel):
    unit_id: int | None = None
    clear_unit: bool = False
    rank: str | None = None
    lock_rank: bool = True
    position: str | None = None
    active: bool | None = None
    note: str | None = None


class SettingsUpdate(BaseModel):
    title: str | None = None
    embed_color: int | None = Field(default=None, ge=0, le=0xFFFFFF)
    rank_source: str | None = Field(default=None, pattern="^(roles|manual)$")
    auto_sync: bool | None = None
