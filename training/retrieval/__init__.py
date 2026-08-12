"""Local reference-grounded design retrieval."""

from training.retrieval.brief import analyze_brief
from training.retrieval.context import build_reference_context, estimate_reference_tokens
from training.retrieval.engine import (
    EmptyReferenceCorpusError,
    ReferenceRetriever,
    RetrievalWeights,
    retrieve_references,
    score_reference,
    reference_structural_similarity,
)
from training.retrieval.hybrid import (
    BoundHybridReferenceRetriever,
    HybridReferenceRetriever,
    HybridRetrievalWeights,
    RetrievalLeakageExclusions,
)
from training.retrieval.features import extract_reference_features, summarize_reference
from training.retrieval.models import (
    ReferenceContextV1,
    ReferenceDesignSummaryV1,
    ReferenceFeaturesV1,
    ReferenceMetadataV1,
    ReferenceRecordV1,
    ReferenceRetrievalResultV1,
    HybridReferenceRetrievalResultV1,
    StructuredBriefV1,
)
from training.retrieval.visual_embeddings import (
    TransformersSiglip2Embedder,
    VisualEmbedder,
    VisualEmbeddingCache,
    cosine_similarity,
    embedding_cache_key,
    normalize_embedding,
)
from training.retrieval.visual_index import (
    VisualEmbeddingIndex,
    VisualEmbeddingIndexV1,
    build_visual_index,
)
from training.retrieval.providers import (
    InternalCdrReferenceProvider,
    JsonlReferenceProvider,
    ReferenceProvider,
)

__all__ = [
    "EmptyReferenceCorpusError",
    "BoundHybridReferenceRetriever",
    "HybridReferenceRetriever",
    "HybridReferenceRetrievalResultV1",
    "HybridRetrievalWeights",
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
    "RetrievalLeakageExclusions",
    "RetrievalWeights",
    "StructuredBriefV1",
    "TransformersSiglip2Embedder",
    "VisualEmbedder",
    "VisualEmbeddingCache",
    "VisualEmbeddingIndex",
    "VisualEmbeddingIndexV1",
    "analyze_brief",
    "build_reference_context",
    "estimate_reference_tokens",
    "extract_reference_features",
    "build_visual_index",
    "cosine_similarity",
    "embedding_cache_key",
    "normalize_embedding",
    "reference_structural_similarity",
    "retrieve_references",
    "score_reference",
    "summarize_reference",
]
