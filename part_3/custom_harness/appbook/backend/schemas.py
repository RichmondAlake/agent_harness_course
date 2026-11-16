"""Request models shared across routers."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TurnReq(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    responder: Literal["claude", "scripted"] | None = None


class ResumeReq(BaseModel):
    thread_id: str
    decisions: dict[str, Literal["approve", "reject"]]
    note: str = ""


class DecisionReq(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = ""


class ClockReq(BaseModel):
    now: str | None = None


class ToolReq(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class DraftReq(ToolReq):
    reason: str = "Drafted by hand in the approvals chapter."


class QueryReq(BaseModel):
    query: str


class QuestionReq(BaseModel):
    question: Literal["urgent", "free", "vip", "overbooked"]


class MemoryReq(BaseModel):
    memory_type: Literal["preference", "guideline", "fact", "person", "commitment"]
    content: str = Field(min_length=1, max_length=1000)
    ttl_days: int | None = Field(None, ge=1, le=730)


class MemoryUpdateReq(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    ttl_days: int | None = Field(None, ge=1, le=730)


class CaptureReq(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class PlanReq(BaseModel):
    content: str


class ScratchFlagReq(BaseModel):
    path: str
    promote: bool
    target: Literal["task", "memory"] | None = None


class ScratchWriteReq(BaseModel):
    path: str
    content: str
    promote_on_end: bool = False
    promote_target: Literal["task", "memory"] = "memory"


class TaskReq(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    priority: int = Field(3, ge=1, le=4)
    due_at: str | None = None
    est_pomodoros: int = Field(1, ge=1, le=8)


class TaskPatchReq(BaseModel):
    title: str | None = None
    priority: int | None = Field(None, ge=1, le=4)
    due_at: str | None = None
    est_pomodoros: int | None = Field(None, ge=1, le=8)


class SnoozeReq(BaseModel):
    until: str | None = None
    hours: int | None = Field(None, ge=1, le=24 * 30)


class ExtractReq(BaseModel):
    thread_ids: list[str] = []


class BlocksReq(BaseModel):
    task_ids: list[str] = []
    date: str | None = None


class FocusStartReq(BaseModel):
    task_id: str | None = None
    minutes: int | None = Field(None, ge=1, le=180)
    demo_seconds: int | None = Field(None, ge=3, le=3600)


class FocusStopReq(BaseModel):
    reason: str = "Stopped from the appbook."


class ConnectReq(BaseModel):
    system: Literal["mail", "calendar", "notes"]
    provider: str
    settings: dict[str, Any] = {}


class SystemReq(BaseModel):
    system: Literal["mail", "calendar", "notes"]


class SwitchReq(BaseModel):
    enabled: bool


class ScheduleReq(BaseModel):
    enabled: bool | None = None
    local_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")


class RunNowReq(BaseModel):
    event_id: str | None = None
    thread_id: str | None = None


class RiskReq(BaseModel):
    to: list[str]
    cc: list[str] = []
    thread_id: str = ""


class WrapReq(BaseModel):
    text: str
    source: str = "mail"
    ref: str = "example"


class SimulateReq(BaseModel):
    days: int = Field(5, ge=1, le=10)


class ResetReq(BaseModel):
    confirm: Literal["reset"]


class DraftSkillReq(BaseModel):
    turn_ids: list[str] = Field(min_length=2, max_length=40)


class ActivateReq(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field("rolled back by the owner", max_length=300)


class ReasonReq(BaseModel):
    reason: str = Field("retired by the owner", max_length=300)


class RefineReq(BaseModel):
    correction: str = Field(min_length=1, max_length=600)
    turn_id: str | None = None


class CorrectionReq(BaseModel):
    text: str = Field(min_length=1, max_length=600)


class CorrectionApplyReq(CorrectionReq):
    destination: Literal["procedure", "preference", "one_off"]
    skill: str | None = None
    turn_id: str | None = None
