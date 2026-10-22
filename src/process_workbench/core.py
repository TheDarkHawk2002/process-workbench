"""Pure validation and analysis logic for process definitions."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class Step:
    step_id: str
    name: str
    duration_minutes: float
    next_steps: tuple[str, ...]


@dataclass(frozen=True)
class ProcessDefinition:
    name: str
    start_step: str
    steps: tuple[Step, ...]
    sample_path: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisReport:
    process_name: str
    start_step: str
    step_count: int
    reachable_steps: tuple[str, ...]
    unreachable_steps: tuple[str, ...]
    cycles: tuple[tuple[str, ...], ...]
    invalid_transitions: tuple[str, ...]
    sample_path: tuple[str, ...]
    sample_path_errors: tuple[str, ...]
    sample_path_complete: bool
    sample_duration_minutes: float | None
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors and not self.invalid_transitions and not self.sample_path_errors

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["valid"] = self.valid
        return result


def parse_definition(document: Any) -> tuple[ProcessDefinition | None, tuple[str, ...]]:
    """Convert untrusted JSON values into a validated, immutable model."""
    errors: list[str] = []
    if not isinstance(document, dict):
        return None, ("Die Prozessdefinition muss ein JSON-Objekt sein.",)

    name = document.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("'name' muss eine nichtleere Zeichenkette sein.")
        name = "(ohne Namen)"

    start_step = document.get("start_step")
    if not isinstance(start_step, str) or not start_step.strip():
        errors.append("'start_step' muss eine nichtleere Schritt-ID sein.")
        start_step = ""

    raw_steps = document.get("steps")
    steps: list[Step] = []
    seen_ids: set[str] = set()
    if not isinstance(raw_steps, list) or not raw_steps:
        errors.append("'steps' muss eine nichtleere Liste sein.")
        raw_steps = []

    for index, raw in enumerate(raw_steps, start=1):
        prefix = f"Schritt {index}"
        if not isinstance(raw, dict):
            errors.append(f"{prefix}: erwartet wird ein JSON-Objekt.")
            continue

        step_id = raw.get("id")
        if not isinstance(step_id, str) or not step_id.strip():
            errors.append(f"{prefix}: 'id' muss eine nichtleere Zeichenkette sein.")
            continue
        step_id = step_id.strip()
        if step_id in seen_ids:
            errors.append(f"{prefix}: doppelte Schritt-ID '{step_id}'.")
            continue
        seen_ids.add(step_id)

        step_name = raw.get("name")
        if not isinstance(step_name, str) or not step_name.strip():
            errors.append(f"Schritt '{step_id}': 'name' muss eine nichtleere Zeichenkette sein.")
            continue

        duration = raw.get("duration_minutes")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not isfinite(duration) or duration < 0:
            errors.append(f"Schritt '{step_id}': 'duration_minutes' muss eine endliche Zahl ab 0 sein.")
            continue

        targets = raw.get("next_steps")
        if not isinstance(targets, list) or any(not isinstance(target, str) or not target.strip() for target in targets):
            errors.append(f"Schritt '{step_id}': 'next_steps' muss eine Liste nichtleerer Schritt-IDs sein.")
            continue
        normalized_targets = tuple(target.strip() for target in targets)
        if len(set(normalized_targets)) != len(normalized_targets):
            errors.append(f"Schritt '{step_id}': 'next_steps' enthält doppelte Ziele.")
            continue

        steps.append(Step(step_id, step_name.strip(), float(duration), normalized_targets))

    sample_path = document.get("sample_path")
    if not isinstance(sample_path, list) or any(not isinstance(item, str) or not item.strip() for item in sample_path):
        errors.append("'sample_path' muss eine Liste nichtleerer Schritt-IDs sein.")
        sample_path = []
    else:
        sample_path = [item.strip() for item in sample_path]

    return ProcessDefinition(name.strip() if isinstance(name, str) else name, start_step, tuple(steps), tuple(sample_path)), tuple(errors)


def _find_cycles(steps_by_id: dict[str, Step]) -> tuple[tuple[str, ...], ...]:
    """Return each directed cycle once, including cycles outside the start path."""
    color: dict[str, int] = {step_id: 0 for step_id in steps_by_id}
    stack: list[str] = []
    stack_positions: dict[str, int] = {}
    found: set[tuple[str, ...]] = set()

    def visit(step_id: str) -> None:
        color[step_id] = 1
        stack_positions[step_id] = len(stack)
        stack.append(step_id)
        for target in sorted(steps_by_id[step_id].next_steps):
            if target not in steps_by_id:
                continue
            if color[target] == 0:
                visit(target)
            elif color[target] == 1:
                cycle = stack[stack_positions[target]:]
                # Canonical rotation avoids reporting the same cycle from a different entry point.
                rotations = [tuple(cycle[offset:] + cycle[:offset]) for offset in range(len(cycle))]
                found.add(min(rotations))
        stack.pop()
        stack_positions.pop(step_id)
        color[step_id] = 2

    for step_id in sorted(steps_by_id):
        if color[step_id] == 0:
            visit(step_id)
    return tuple(sorted(found))


def analyze(definition: ProcessDefinition, parse_errors: tuple[str, ...] = ()) -> AnalysisReport:
    steps_by_id = {step.step_id: step for step in definition.steps}
    invalid_transitions: list[str] = []
    for step in definition.steps:
        for target in step.next_steps:
            if target not in steps_by_id:
                invalid_transitions.append(f"'{step.step_id}' verweist auf unbekanntes Ziel '{target}'.")

    if definition.start_step not in steps_by_id:
        parse_errors = (*parse_errors, f"Startschritt '{definition.start_step}' existiert nicht.")

    reachable: set[str] = set()
    if definition.start_step in steps_by_id:
        pending = deque([definition.start_step])
        while pending:
            step_id = pending.popleft()
            if step_id in reachable:
                continue
            reachable.add(step_id)
            pending.extend(
                target for target in steps_by_id[step_id].next_steps
                if target in steps_by_id and target not in reachable
            )

    path_errors: list[str] = []
    path = definition.sample_path
    if not path:
        path_errors.append("Der Beispielablauf ist leer.")
    elif path[0] != definition.start_step:
        path_errors.append(f"Der Beispielablauf muss mit dem Startschritt '{definition.start_step}' beginnen.")
    for index, step_id in enumerate(path):
        if step_id not in steps_by_id:
            path_errors.append(f"Beispielschritt '{step_id}' existiert nicht.")
            continue
        if index + 1 < len(path):
            next_id = path[index + 1]
            if next_id not in steps_by_id[step_id].next_steps:
                path_errors.append(f"Übergang '{step_id}' → '{next_id}' ist nicht definiert.")

    complete = bool(path) and path[-1] in steps_by_id and not steps_by_id[path[-1]].next_steps
    if path and path[-1] in steps_by_id and not complete:
        path_errors.append(f"Der Beispielablauf endet bei '{path[-1]}', obwohl dort noch Übergänge offen sind.")
    duration = None
    if path and all(step_id in steps_by_id for step_id in path):
        duration = sum(steps_by_id[step_id].duration_minutes for step_id in path)

    return AnalysisReport(
        process_name=definition.name,
        start_step=definition.start_step,
        step_count=len(definition.steps),
        reachable_steps=tuple(sorted(reachable)),
        unreachable_steps=tuple(sorted(set(steps_by_id) - reachable)),
        cycles=_find_cycles(steps_by_id),
        invalid_transitions=tuple(sorted(invalid_transitions)),
        sample_path=path,
        sample_path_errors=tuple(path_errors),
        sample_path_complete=complete and not path_errors,
        sample_duration_minutes=duration,
        errors=parse_errors,
    )
