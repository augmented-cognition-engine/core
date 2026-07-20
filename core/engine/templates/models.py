"""Pydantic models for initiative templates.

A template is a saved initiative blueprint: milestone structure with
work item templates, and variables ({{variable_name}} substitution).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateVariable(BaseModel):
    name: str
    type: str = "string"
    prompt: str
    default: str | None = None


class TemplateWorkItem(BaseModel):
    title: str
    archetype: str
    mode: str
    domain_path: str
    description: str = ""
    requires_human: bool = False


class TemplateMilestone(BaseModel):
    title: str
    description: str = ""
    done_criteria: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    work_items: list[TemplateWorkItem] = Field(default_factory=list)


class Template(BaseModel):
    name: str
    description: str
    domain_path: str
    variables: list[TemplateVariable] = Field(default_factory=list)
    milestones: list[TemplateMilestone] = Field(default_factory=list)
