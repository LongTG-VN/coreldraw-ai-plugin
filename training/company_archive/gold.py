"""Fail-closed bridge from human-certified company CDR data to Gold grammar."""

from __future__ import annotations

from training.company_archive.models import ArchiveFileRecord, GoldStatus
from training.gold.extractor import GoldGrammarExtractor
from training.schemas.design import DesignDocument
from training.schemas.gold import GoldDesignGrammarV1


def extract_company_gold_grammar(
    document: DesignDocument,
    source_record: ArchiveFileRecord,
    *,
    grammar_id: str,
    grammar_name: str,
) -> GoldDesignGrammarV1:
    if source_record.gold_status != GoldStatus.HUMAN_CERTIFIED_GOLD:
        raise ValueError("company grammar extraction requires HUMAN_CERTIFIED_GOLD")
    if document.source.upstream_id != source_record.sha256:
        raise ValueError("DesignDocument SHA256 provenance does not match inventory record")
    if document.metadata.get("source_type") != "COMPANY_OWNED_CDR":
        raise ValueError("Gold input must originate from a company-owned CDR extraction")
    grammar = GoldGrammarExtractor().extract(document, grammar_id, grammar_name)
    grammar.gold_status = "HUMAN_CERTIFIED"
    grammar.provenance.update(
        {
            "source_type": "COMPANY_OWNED_CDR",
            "source_file_id": source_record.file_id,
            "source_sha256": source_record.sha256,
            "project_owned": True,
            "human_quality_status": source_record.human_quality_status.value,
            "human_reviewer": source_record.human_reviewer,
            "commercial_allowed": source_record.commercial_allowed,
            "rights_status": source_record.rights_status.value,
        }
    )
    return grammar

