"""Command-line interface for the process workbench."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Sequence

from .core import AnalysisReport, analyze, parse_definition


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process-workbench",
        description="Validate a JSON process graph and summarize a reproducible example flow.",
    )
    parser.add_argument("definition", type=Path, help="Path to the process definition (JSON)")
    parser.add_argument("--report", type=Path, help="Write an additional .json, .csv, or .txt report")
    return parser


def _format_text(report: AnalysisReport) -> str:
    lines = [
        f"Prozess: {report.process_name}",
        f"Startschritt: {report.start_step}",
        f"Schritte: {report.step_count}",
        f"Erreichbar: {', '.join(report.reachable_steps) or 'keine'}",
        f"Unerreichbar: {', '.join(report.unreachable_steps) or 'keine'}",
        f"Beispielablauf: {' -> '.join(report.sample_path) or 'nicht angegeben'}",
        f"Ablauf vollständig: {'ja' if report.sample_path_complete else 'nein'}",
        "Dauer des Beispielablaufs: " + (
            f"{report.sample_duration_minutes:g} Minuten" if report.sample_duration_minutes is not None else "nicht berechenbar"
        ),
        f"Ergebnis: {'gültig' if report.valid else 'mit Fehlern'}",
    ]
    if report.cycles:
        lines.append("Zyklen: " + "; ".join(" -> ".join((*cycle, cycle[0])) for cycle in report.cycles))
    if report.invalid_transitions:
        lines.extend(f"Fehler Übergang: {item}" for item in report.invalid_transitions)
    if report.sample_path_errors:
        lines.extend(f"Fehler Beispielablauf: {item}" for item in report.sample_path_errors)
    if report.errors:
        lines.extend(f"Fehler Definition: {item}" for item in report.errors)
    return "\n".join(lines)


def _write_report(path: Path, source: Path, report: AnalysisReport) -> None:
    target = path.expanduser().resolve()
    if target == source.expanduser().resolve():
        raise ValueError("Der Bericht darf die Quelldatei nicht überschreiben.")
    formats = {".json": "json", ".csv": "csv", ".txt": "txt"}
    kind = formats.get(target.suffix.lower())
    if kind is None:
        raise ValueError("Das Berichtsformat muss aus der Dateiendung .json, .csv oder .txt hervorgehen.")

    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of existing work.
    with target.open("x", encoding="utf-8", newline="") as stream:
        if kind == "json":
            json.dump(report.to_dict(), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        elif kind == "csv":
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Merkmal", "Wert"])
            for key, value in report.to_dict().items():
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                writer.writerow([key, value])
        else:
            stream.write(_format_text(report) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    # Keep German status messages readable in Windows terminals with a legacy code page.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    source = args.definition.expanduser()
    try:
        with source.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
    except OSError as exc:
        print(f"Fehler beim Lesen von '{source}': {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Ungültiges JSON in '{source}' (Zeile {exc.lineno}, Spalte {exc.colno}): {exc.msg}", file=sys.stderr)
        return 1

    definition, parse_errors = parse_definition(document)
    if definition is None:
        print("\n".join(f"Fehler: {item}" for item in parse_errors), file=sys.stderr)
        return 1
    report = analyze(definition, parse_errors)
    print(_format_text(report))

    if args.report:
        try:
            _write_report(args.report, source, report)
            print(f"Bericht geschrieben: {args.report}")
        except (OSError, ValueError) as exc:
            print(f"Bericht konnte nicht geschrieben werden: {exc}", file=sys.stderr)
            return 2
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
