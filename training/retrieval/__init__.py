"""Local reference-grounded design retrieval."""

from training.retrieval.brief import analyze_brief
from training.retrieval.context import build_reference_context, estimate_reference_tokens
from training.retrieval.engine import (
    EmptyReferenceCorpusError,
    ReferenceRetriever,
    RetrievalWeights,
    retrieve_references,
)
from training.retrieval.features import extract_reference_features, summarize_reference
from training.retrieval.models import (
    ReferenceContextV1,
    ReferenceDesignSummaryV1,
    ReferenceFeaturesV1,
    ReferenceMetadataV1,
    ReferenceRecordV1,
    ReferenceRetrievalResultV1,
    StructuredBriefV1,
)
from training.retrieval.providers import (
    InternalCdrReferenceProvider,
    JsonlReferenceProvider,
    ReferenceProvider,
)

__all__ = [
    "EmptyReferenceCorpusError",
    "InternalCdrReferenceProvider",
    "JsonlReferenceProvider",
    "ReferenceContextV1",
    "ReferenceDesignSummaryV1",
    "ReferenceFeaturesV1",
    "ReferenceMetadataV1",
    "ReferenceProvider",
    "ReferenceRecordV1",
    "ReferenceRetrievalResultV1",
    "ReferenceRetriever",
    "RetrievalWeights",
    "StructuredBriefV1",
    "analyze_brief",
    "build_reference_context",
    "estimate_reference_tokens",
    "extract_reference_features",
    "retrieve_references",
    "summarize_reference",
]
