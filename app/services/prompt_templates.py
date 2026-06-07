"""Prompt template rendering and storage helpers."""

from __future__ import annotations

import re
from difflib import unified_diff
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import PromptTemplate

_VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class PromptTemplateError(ValueError):
    """Raised when prompt templates cannot be rendered or resolved."""


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        raise PromptTemplateError(f"Missing prompt variable: {key}")


def infer_template_variables(template_text: str) -> list[str]:
    seen: list[str] = []
    for match in _VARIABLE_PATTERN.findall(template_text):
        if match not in seen:
            seen.append(match)
    return seen


def render_template_text(template_text: str, variables: dict[str, Any]) -> str:
    try:
        return template_text.format_map(_SafeFormatDict(variables))
    except PromptTemplateError:
        raise
    except Exception as exc:
        raise PromptTemplateError(str(exc)) from exc


@dataclass
class PromptTemplateCreateInput:
    name: str
    template_text: str
    description: str | None = None
    variables: list[str] | None = None
    model_override: str | None = None
    metadata: dict[str, Any] | None = None


def list_prompt_templates(session: Session) -> list[PromptTemplate]:
    statement: Select[tuple[PromptTemplate]] = select(PromptTemplate).order_by(PromptTemplate.name.asc(), PromptTemplate.version.desc())
    return list(session.execute(statement).scalars().all())


def get_prompt_template(session: Session, *, name: str, version: int | None = None) -> PromptTemplate | None:
    statement = select(PromptTemplate).where(PromptTemplate.name == name)
    if version is not None:
        statement = statement.where(PromptTemplate.version == version)
    else:
        statement = statement.order_by(PromptTemplate.version.desc())
    return session.execute(statement.limit(1)).scalars().first()


def create_prompt_template(session: Session, payload: PromptTemplateCreateInput) -> PromptTemplate:
    next_version = (
        session.execute(select(func.coalesce(func.max(PromptTemplate.version), 0)).where(PromptTemplate.name == payload.name))
        .scalar_one()
        + 1
    )
    variables = payload.variables or infer_template_variables(payload.template_text)
    record = PromptTemplate(
        id=f"prompttpl_{uuid4().hex}",
        name=payload.name,
        version=int(next_version),
        description=payload.description,
        template_text=payload.template_text,
        variables_json=variables,
        model_override=payload.model_override,
        metadata_json=payload.metadata or {},
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def prompt_template_payload(item: PromptTemplate) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "version": item.version,
        "description": item.description,
        "template_text": item.template_text,
        "variables": list(item.variables_json or []),
        "model_override": item.model_override,
        "metadata": item.metadata_json or {},
        "created_at": item.created_at,
    }


def render_prompt_template(
    session: Session,
    *,
    name: str,
    version: int | None = None,
    variables: dict[str, Any] | None = None,
) -> tuple[PromptTemplate, str]:
    record = get_prompt_template(session, name=name, version=version)
    if record is None:
        raise PromptTemplateError("Prompt template not found.")
    rendered = render_template_text(record.template_text, variables or {})
    return record, rendered


def diff_prompt_templates(
    session: Session,
    *,
    name: str,
    from_version: int,
    to_version: int,
) -> dict[str, Any]:
    left = get_prompt_template(session, name=name, version=from_version)
    right = get_prompt_template(session, name=name, version=to_version)
    if left is None or right is None:
        raise PromptTemplateError("Prompt template version not found.")
    diff_lines = list(
        unified_diff(
            left.template_text.splitlines(),
            right.template_text.splitlines(),
            fromfile=f"{name}@v{from_version}",
            tofile=f"{name}@v{to_version}",
            lineterm="",
        )
    )
    return {
        "name": name,
        "from_version": from_version,
        "to_version": to_version,
        "from_variables": list(left.variables_json or []),
        "to_variables": list(right.variables_json or []),
        "from_model_override": left.model_override,
        "to_model_override": right.model_override,
        "unified_diff": "\n".join(diff_lines),
    }
