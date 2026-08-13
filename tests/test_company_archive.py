from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from training.company_archive.classify import classify_extension
from training.company_archive.curation import curate_file
from training.company_archive.curation_app import create_curation_app
from training.company_archive.database import ArchiveDatabase
from training.company_archive.duplicates import (
    bind_full_sha256,
    fingerprint_candidates,
    verify_duplicate_groups,
)
from training.company_archive.extractor import inspection_to_design_document
from training.company_archive.hashing import fast_fingerprint, sha256_file
from training.company_archive.gold import extract_company_gold_grammar
from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.models import (
    ArchiveCategory,
    ArchiveFileRecord,
    CdrInspectionV1,
    CdrObjectV1,
    GoldStatus,
    HumanQualityStatus,
    RightsStatus,
    WorkStatus,
)
from training.company_archive.previews import PreviewBatcher
from training.company_archive.scanner import ArchiveScanner
from training.company_archive.safety import ArchiveSafetyError, resolve_archive_paths
from training.inference.corel_compiler import compile_corel_operations


def _record(path: Path, root: Path, *, file_id: str = "file:" + "a" * 32) -> ArchiveFileRecord:
    stat = path.stat()
    return ArchiveFileRecord(
        file_id=file_id,
        absolute_path=str(path.resolve()),
        relative_path=path.relative_to(root).as_posix(),
        filename=path.name,
        extension=path.suffix,
        size_bytes=stat.st_size,
        modified_time=stat.st_mtime,
        created_time=stat.st_ctime,
        file_type="CDR",
        cdr_candidate=True,
    )


def _inspection(source: Path) -> CdrInspectionV1:
    stat = source.stat()
    return CdrInspectionV1(
        source_path=str(source.resolve()),
        source_size_bytes=stat.st_size,
        source_mtime_ns=stat.st_mtime_ns,
        corel_version="fixture",
        page_count=1,
        page_width=210,
        page_height=297,
        unit="mm",
        corel_unit_code=3,
        layer_count=1,
        object_count=2,
        text_object_count=1,
        bitmap_count=0,
        vector_count=1,
        group_count=0,
        font_families=["Arial"],
        objects=[
            CdrObjectV1(
                object_id="headline",
                corel_name="headline",
                object_type="text",
                bbox={"x": 10, "y": 20, "width": 100, "height": 20},
                bbox_norm={"x": 10 / 210, "y": 20 / 297, "width": 100 / 210, "height": 20 / 297},
                z_index=2,
                text="Company design",
                font_family="Arial",
                font_size=18,
                alignment="left",
                fill={"model": "cmyk", "values": [0, 0, 0, 100]},
            ),
            CdrObjectV1(
                object_id="panel",
                corel_name="panel",
                object_type="rectangle",
                bbox={"x": 5, "y": 5, "width": 200, "height": 287},
                bbox_norm={"x": 5 / 210, "y": 5 / 297, "width": 200 / 210, "height": 287 / 297},
                z_index=1,
                fill={"model": "cmyk", "values": [0, 5, 10, 0]},
            ),
        ],
        source_save_called=False,
    )


def test_archive_paths_must_be_disjoint(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    with pytest.raises(ArchiveSafetyError, match="disjoint"):
        resolve_archive_paths(root, root / "workspace")


def test_scanner_is_resumable_and_persists_inventory(tmp_path: Path) -> None:
    root = tmp_path / "source"
    workspace = tmp_path / "workspace"
    root.mkdir()
    for index, suffix in enumerate((".cdr", ".pdf", ".jpg", ".txt", ".cdt")):
        (root / f"{index}{suffix}").write_bytes(bytes([index]) * (index + 1))
    before = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in root.iterdir()}

    scanner = ArchiveScanner(root, workspace)
    first = scanner.scan(limit=2)
    assert first.completed is False
    assert first.scanned_files == 2
    second = scanner.scan()
    assert second.resumed is True
    assert second.completed is True
    assert second.total_files == 5
    assert second.cdr_count == 2
    assert second.pdf_count == 1
    assert second.image_count == 1
    assert ArchiveDatabase(workspace / "archive.sqlite").statistics()["total_files"] == 5
    after = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in root.iterdir()}
    assert before == after


def test_file_type_classification() -> None:
    assert classify_extension(".cdr")[1] is True
    assert classify_extension(".CDT")[1] is True
    assert classify_extension(".pdf")[2] is True
    assert classify_extension(".jpeg")[3] is True
    assert classify_extension(".psd")[0].value == "OTHER"


def test_hashes_and_duplicate_grouping_are_verified(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    one = root / "one.cdr"
    two = root / "two.cdr"
    three = root / "three.cdr"
    one.write_bytes(b"real-test-content")
    two.write_bytes(b"real-test-content")
    three.write_bytes(b"different-content!")
    workspace = tmp_path / "workspace"
    scanner = ArchiveScanner(root, workspace)
    scanner.scan()
    db = scanner.database

    assert fast_fingerprint(one) == fast_fingerprint(two)
    assert sha256_file(one) == sha256_file(two)
    # Stage B only fingerprints cheap candidates sharing the same byte size.
    assert fingerprint_candidates(db) == 2
    assert verify_duplicate_groups(db) == 1
    duplicate_rows = db.rows("duplicate_group_id IS NOT NULL")
    assert len(duplicate_rows) == 2
    assert len({row["sha256"] for row in duplicate_rows}) == 1
    assert all(row["duplicate_confidence"] == "SHA256_VERIFIED" for row in duplicate_rows)


def test_human_certification_and_rights_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    source = root / "design.cdr"
    source.write_bytes(b"fixture")
    db = ArchiveDatabase(tmp_path / "workspace" / "archive.sqlite")
    db.upsert_file(_record(source, root), scan_id="test")

    with pytest.raises(ValueError, match="human UI"):
        curate_file(
            db,
            file_id="file:" + "a" * 32,
            reviewer="Reviewer",
            quality=HumanQualityStatus.APPROVE,
            source="heuristic",
        )
    with pytest.raises((ValueError, ValidationError), match="company ownership"):
        curate_file(
            db,
            file_id="file:" + "a" * 32,
            reviewer="Reviewer",
            quality=HumanQualityStatus.APPROVE,
            gold_status=GoldStatus.HUMAN_CERTIFIED_GOLD,
        )

    certified = curate_file(
        db,
        file_id="file:" + "a" * 32,
        reviewer="Reviewer",
        quality=HumanQualityStatus.APPROVE,
        category=ArchiveCategory.SALE,
        gold_status=GoldStatus.HUMAN_CERTIFIED_GOLD,
        rights_status=RightsStatus.CONFIRMED_COMPANY_OWNED,
        commercial_allowed=False,
    )
    assert certified.sha256 == sha256_file(source)
    assert certified.gold_status == GoldStatus.HUMAN_CERTIFIED_GOLD
    assert certified.commercial_allowed is False


class _FakeInspector:
    def render_preview(self, path: Path, output: Path, *, archive_root: Path, dpi: int):
        assert archive_root in path.resolve().parents
        Image.new("RGB", (120, 80), "white").save(output)
        return output


def test_preview_batch_is_bounded_and_records_dimensions(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    source = root / "design.cdr"
    source.write_bytes(b"fixture")
    workspace = tmp_path / "workspace"
    db = ArchiveDatabase(workspace / "archive.sqlite")
    record = _record(source, root)
    db.upsert_file(record, scan_id="test")
    before = source.stat().st_mtime_ns

    with pytest.raises(ValueError, match="explicit"):
        PreviewBatcher(db, workspace, inspector=_FakeInspector()).render(archive_root=root)
    results = PreviewBatcher(db, workspace, inspector=_FakeInspector()).render(
        archive_root=root, file_ids=[record.file_id], limit=1
    )
    assert results[0]["status"] == "COMPLETE"
    updated = db.get_file(record.file_id)
    assert updated["preview_width"] == 120
    assert updated["preview_height"] == 80
    assert source.stat().st_mtime_ns == before


class _Collection:
    def __init__(self, values):
        self.values = values
        self.Count = len(values)

    def __iter__(self):
        return iter(self.values)

    def Item(self, index):
        return self.values[index - 1]


class _Shape:
    def __init__(self, name: str, type_code: int, *, text: str | None = None):
        self.Name = name
        self.Type = type_code
        self.LeftX = 10
        self.BottomY = 250
        self.SizeWidth = 80
        self.SizeHeight = 20
        self.RotationAngle = 0
        self.Layer = SimpleNamespace(Name="Layer 1")
        self.Shapes = _Collection([])
        self.Fill = SimpleNamespace(
            UniformColor=SimpleNamespace(CMYKCyan=0, CMYKMagenta=0, CMYKYellow=0, CMYKBlack=100)
        )
        if text is not None:
            self.Text = SimpleNamespace(
                Story=SimpleNamespace(Text=text, Font="Arial", Size=18, Alignment="left")
            )


class _OpenedDocument:
    def __init__(self):
        shapes = _Collection(
            [
                _Shape("headline", 6, text="Editable"),
                _Shape("panel", 1),
                _Shape("panel", 1),
            ]
        )
        self.ActivePage = SimpleNamespace(
            SizeWidth=210,
            SizeHeight=297,
            Shapes=shapes,
            ActiveLayer=SimpleNamespace(Shapes=shapes),
            Layers=_Collection([SimpleNamespace(Name="Layer 1")]),
        )
        self.Pages = _Collection([self.ActivePage])
        self.Unit = 3
        self.Version = "fixture"
        self.closed = False
        self.save_called = False

    def Close(self):
        self.closed = True

    def Save(self):
        self.save_called = True
        raise AssertionError("source Save must never be called")


class _FakeBridge:
    def __init__(self, source: Path):
        self.opened = _OpenedDocument()
        self.application = SimpleNamespace(Version="fixture-corel", ActiveDocument=None)

        def open_document(_path):
            self.application.ActiveDocument = self.opened
            return SimpleNamespace(command="OpenDocument")

        self.application.OpenDocument = open_document
        self.active = SimpleNamespace(FullFileName=str(source.parent / "other.cdr"))

    @contextmanager
    def session(self):
        yield self.application, self.active


def test_cdr_inspector_closes_without_saving_source(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    source = root / "design.cdr"
    source.write_bytes(b"fixture")
    before = (source.stat().st_size, source.stat().st_mtime_ns)
    bridge = _FakeBridge(source)

    result = CompanyCdrInspector(bridge).inspect(source, archive_root=root)

    assert result.object_count == 3
    assert result.text_object_count == 1
    assert result.vector_count == 2
    assert len({item.object_id for item in result.objects}) == 3
    assert result.unit == "mm"
    assert result.source_save_called is False
    assert bridge.opened.closed is True
    assert bridge.opened.save_called is False
    assert before == (source.stat().st_size, source.stat().st_mtime_ns)


def test_cdr_inspection_maps_to_normalized_design_and_corel_operations(tmp_path: Path) -> None:
    source = tmp_path / "real.cdr"
    source.write_bytes(b"fixture")
    inspection = _inspection(source)
    digest = sha256_file(source)

    document = inspection_to_design_document(
        inspection,
        source_sha256=digest,
        category="SALE",
        rights_status=RightsStatus.UNKNOWN,
        commercial_allowed=False,
    )

    assert document.metadata["source_type"] == "COMPANY_OWNED_CDR"
    assert document.metadata["project_owned"] is False
    assert document.source.commercial_allowed is False
    assert document.elements[0].bbox_norm.x == pytest.approx(10 / 210)
    assert document.elements[0].text.font_family == "Arial"
    assert document.elements[0].text.font_size == 18
    assert len(compile_corel_operations(document)) == 3

    inch_document = inspection_to_design_document(
        inspection.model_copy(update={"unit": "in", "corel_unit_code": 1}),
        source_sha256=digest,
        category="SALE",
    )
    assert inch_document.elements[0].bbox.x == pytest.approx(254)
    assert inch_document.elements[0].text.font_size == 18


def test_gold_grammar_requires_human_certified_sha_bound_company_source(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    source = root / "real.cdr"
    source.write_bytes(b"fixture")
    db = ArchiveDatabase(tmp_path / "workspace" / "archive.sqlite")
    record = _record(source, root)
    db.upsert_file(record, scan_id="test")
    certified = curate_file(
        db,
        file_id=record.file_id,
        reviewer="Human Reviewer",
        quality=HumanQualityStatus.APPROVE,
        gold_status=GoldStatus.HUMAN_CERTIFIED_GOLD,
        rights_status=RightsStatus.CONFIRMED_COMPANY_OWNED,
    )
    document = inspection_to_design_document(
        _inspection(source),
        source_sha256=certified.sha256,
        category="SALE",
        rights_status=RightsStatus.CONFIRMED_COMPANY_OWNED,
    )
    grammar = extract_company_gold_grammar(
        document,
        certified,
        grammar_id="company-gold-001",
        grammar_name="Human certified fixture",
    )
    assert grammar.gold_status == "HUMAN_CERTIFIED"
    assert grammar.provenance["source_sha256"] == certified.sha256
    assert grammar.provenance["project_owned"] is True
    assert grammar.provenance["commercial_allowed"] is False


def test_extraction_rights_and_unknown_units_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "real.cdr"
    source.write_bytes(b"fixture")
    inspection = _inspection(source)
    with pytest.raises(ValueError, match="commercial"):
        inspection_to_design_document(
            inspection,
            source_sha256=sha256_file(source),
            category="SALE",
            commercial_allowed=True,
        )
    invalid = inspection.model_copy(update={"unit": "unknown"})
    with pytest.raises(ValueError, match="unsupported Corel document unit"):
        inspection_to_design_document(
            invalid,
            source_sha256=sha256_file(source),
            category="SALE",
        )


def test_curation_preview_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    root = tmp_path / "source"
    root.mkdir()
    source = root / "design.cdr"
    source.write_bytes(b"fixture")
    outside = tmp_path / "outside.png"
    Image.new("RGB", (10, 10)).save(outside)
    db = ArchiveDatabase(workspace / "archive.sqlite")
    record = _record(source, root)
    db.upsert_file(record, scan_id="test")
    db.update_fields(
        record.file_id,
        preview_status=WorkStatus.COMPLETE,
        preview_path=str(outside),
        preview_width=10,
        preview_height=10,
    )
    client = TestClient(create_curation_app(db, workspace))
    assert client.get(f"/api/v1/company-curation/preview/{record.file_id}").status_code == 404


def test_company_archive_code_never_writes_fake_cdr_bytes() -> None:
    root = Path("training/company_archive")
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert ".write_bytes(" not in source
    assert "open(\"wb\")" not in source
    assert "open('wb')" not in source
