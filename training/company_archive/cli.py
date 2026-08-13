"""CLI for bounded, read-only company archive bootstrap operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.company_archive.curation_app import create_curation_app
from training.company_archive.database import ArchiveDatabase
from training.company_archive.duplicates import (
    bind_full_sha256,
    fingerprint_candidates,
    verify_duplicate_groups,
)
from training.company_archive.extractor import CompanyCdrExtractor
from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.models import RightsStatus, WorkStatus
from training.company_archive.previews import PreviewBatcher
from training.company_archive.scanner import ArchiveScanner
from training.company_archive.safety import resolve_archive_paths
from training.inference.corel_compiler import compile_corel_operations


def _workspace(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _database(workspace: Path) -> ArchiveDatabase:
    return ArchiveDatabase(workspace / "archive.sqlite")


def _require_read_only(args: argparse.Namespace) -> None:
    if not args.read_only:
        raise SystemExit("--read-only is required; source archives are immutable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser("inventory", help="metadata-first resumable scan")
    inventory.add_argument("--root", type=Path, required=True)
    inventory.add_argument("--workspace", type=Path, required=True)
    inventory.add_argument("--read-only", action="store_true")
    inventory.add_argument("--limit", type=int)
    inventory.add_argument("--no-resume", action="store_true")

    duplicates = sub.add_parser("duplicates", help="staged duplicate grouping")
    duplicates.add_argument("--workspace", type=Path, required=True)

    previews = sub.add_parser("previews", help="bounded Corel preview batch")
    previews.add_argument("--root", type=Path, required=True)
    previews.add_argument("--workspace", type=Path, required=True)
    previews.add_argument("--read-only", action="store_true")
    previews.add_argument("--file-id", action="append", default=[])
    previews.add_argument("--limit", type=int)
    previews.add_argument("--dpi", type=int, default=96)

    inspect = sub.add_parser("inspect", help="inspect one CDR and close without save")
    inspect.add_argument("--root", type=Path, required=True)
    inspect.add_argument("--workspace", type=Path, required=True)
    inspect.add_argument("--read-only", action="store_true")
    inspect.add_argument("--file-id", required=True)

    extract = sub.add_parser("extract", help="prototype one CDR to DesignDocument")
    extract.add_argument("--root", type=Path, required=True)
    extract.add_argument("--workspace", type=Path, required=True)
    extract.add_argument("--read-only", action="store_true")
    extract.add_argument("--file-id", required=True)
    extract.add_argument("--category", default="OTHER")
    extract.add_argument("--confirm-company-rights", action="store_true")
    extract.add_argument("--commercial-allowed", action="store_true")

    serve = sub.add_parser("serve-curation", help="local human archive curation UI")
    serve.add_argument("--workspace", type=Path, required=True)
    serve.add_argument("--host", choices=["127.0.0.1", "localhost"], default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8005)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workspace = _workspace(str(args.workspace))

    if args.command == "inventory":
        _require_read_only(args)
        scanner = ArchiveScanner(args.root, workspace)
        summary = scanner.scan(limit=args.limit, resume=not args.no_resume)
        print(summary.model_dump_json(indent=2))
        return 0

    database = _database(workspace)
    if args.command == "duplicates":
        print(json.dumps({
            "fingerprinted": fingerprint_candidates(database),
            "verified_duplicate_groups": verify_duplicate_groups(database),
        }, indent=2))
        return 0

    if args.command == "previews":
        _require_read_only(args)
        root, _ = resolve_archive_paths(args.root, workspace)
        results = PreviewBatcher(database, workspace).render(
            archive_root=root,
            file_ids=args.file_id,
            limit=args.limit,
            dpi=args.dpi,
        )
        print(json.dumps(results, indent=2))
        return 0 if all(row["status"] == "COMPLETE" for row in results) else 2

    if args.command in {"inspect", "extract"}:
        _require_read_only(args)
        root, _ = resolve_archive_paths(args.root, workspace)
        row = database.get_file(args.file_id)
        source = Path(row["absolute_path"])
        inspector = CompanyCdrInspector()
        inspection = inspector.inspect(source, archive_root=root)
        inspection_json = inspection.model_dump_json(indent=2)
        database.update_fields(
            args.file_id,
            corel_inspection_status=WorkStatus.COMPLETE,
            inspection_json=inspection_json,
        )
        inspection_root = workspace / "inspections"
        inspection_root.mkdir(parents=True, exist_ok=True)
        inspection_path = inspection_root / f"{args.file_id.removeprefix('file:')}.json"
        inspection_path.write_text(inspection_json + "\n", encoding="utf-8")
        if args.command == "inspect":
            print(inspection_json)
            return 0

        rights = (
            RightsStatus.CONFIRMED_COMPANY_OWNED
            if args.confirm_company_rights
            else RightsStatus.UNKNOWN
        )
        document, _ = CompanyCdrExtractor(inspector).extract(
            source,
            archive_root=root,
            category=args.category,
            rights_status=rights,
            commercial_allowed=args.commercial_allowed,
            inspection=inspection,
        )
        bound_sha256 = bind_full_sha256(database, args.file_id)
        if bound_sha256 != document.source.upstream_id:
            raise RuntimeError("inventory SHA256 binding changed during extraction")
        extraction_root = workspace / "extractions" / args.file_id.removeprefix("file:")
        extraction_root.mkdir(parents=True, exist_ok=True)
        design_path = extraction_root / "design.json"
        design_path.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
        supported = all(item.type != "other" for item in document.elements)
        operations = compile_corel_operations(document) if supported else None
        report = {
            "source_file_id": args.file_id,
            "source_sha256": document.source.upstream_id,
            "design_path": str(design_path),
            "schema_valid": True,
            "object_count": len(document.elements),
            "current_compiler_complete": supported,
            "corel_operation_count": len(operations) if operations else None,
            "round_trip_status": "READY_FOR_DISPOSABLE_COPY" if supported else "BLOCKED_UNSUPPORTED_OBJECTS",
            "company_sample_human_approved": False,
        }
        if operations is not None:
            (extraction_root / "corel_operations.json").write_text(
                json.dumps(operations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        (extraction_root / "extraction_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
        return 0

    if args.command == "serve-curation":
        import uvicorn
        app = create_curation_app(database, workspace)
        print(f"Open:\nhttp://127.0.0.1:{args.port}/curation")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
