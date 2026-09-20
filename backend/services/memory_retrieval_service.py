"""Shared contracts and observability helpers for memory retrieval.

Phase 1 deliberately keeps the existing retrieval algorithms in place.  This
module gives lexical, vector, and graph implementations a common boundary so a
hybrid retriever can be introduced without changing Context Pack consumers.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


RETRIEVAL_CONTRACT_VERSION = "memory-candidate.v1"
RETRIEVAL_STRATEGY_VERSION = "hybrid-retrieval.v2"
HYBRID_FUSION_VERSION = "weighted-rrf.v1"
RETRIEVAL_CHANNEL_ORDER = ("structured", "lexical", "vector", "graph")
RETRIEVAL_CHANNELS = set(RETRIEVAL_CHANNEL_ORDER)
DEFAULT_CHANNEL_WEIGHTS = {
    "structured": 1.25,
    "lexical": 1.0,
    "vector": 1.1,
    "graph": 0.75,
}
IMPORTANCE_WEIGHTS = {
    "critical": 1.0,
    "high": 0.85,
    "normal": 0.65,
    "low": 0.4,
}


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(max(0.0, min(number, 1.0)), 4)


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RetrievalScope:
    user_id: str = ""
    project_id: str = ""
    agent_id: str = ""
    visibility: str = "private"

    def as_dict(self) -> dict[str, str]:
        return {
            "user_id": self.user_id,
            "project_id": self.project_id,
            "agent_id": self.agent_id,
            "visibility": self.visibility,
        }


@dataclass
class MemoryCandidate:
    """Storage-neutral memory candidate used by every retrieval channel."""

    source_type: str
    source_id: str
    source_ref: str
    title: str
    content: str
    final_score: float
    confidence: float
    channel: str
    scope: RetrievalScope = field(default_factory=RetrievalScope)
    channel_scores: dict[str, float] = field(default_factory=dict)
    authority_score: float = 0.5
    importance: str = "normal"
    status: str = "active"
    updated_at: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.channel not in RETRIEVAL_CHANNELS:
            raise ValueError(f"unsupported retrieval channel: {self.channel}")
        if not self.source_ref.strip():
            raise ValueError("memory candidate requires source_ref")
        if not self.content.strip():
            raise ValueError("memory candidate requires content")

    @property
    def candidate_id(self) -> str:
        return f"memory-candidate:{_stable_hash((self.source_type, self.source_ref))[:20]}"

    @property
    def content_hash(self) -> str:
        return _stable_hash(self.content)

    def to_context_item(self) -> dict[str, Any]:
        scores = {
            channel: _clamp(score)
            for channel, score in self.channel_scores.items()
            if channel in RETRIEVAL_CHANNELS
        }
        scores.setdefault(self.channel, _clamp(self.final_score))
        scores["final"] = _clamp(self.final_score)
        retrieval = {
            "contract_version": RETRIEVAL_CONTRACT_VERSION,
            "candidate_id": self.candidate_id,
            "primary_channel": self.channel,
            "channels": sorted(scores.keys() - {"final"}),
            "scores": scores,
            "authority_score": _clamp(self.authority_score),
            "importance": self.importance,
            "status": self.status,
            "scope": self.scope.as_dict(),
            "updated_at": self.updated_at,
            "content_hash": self.content_hash,
        }
        return {
            "item_type": self.source_type,
            "source_id": self.source_id,
            "source_ref": self.source_ref,
            "title": self.title[:300],
            "content": self.content[:8000],
            "score": _clamp(self.final_score),
            "confidence": _clamp(self.confidence, 1.0),
            "metadata": {**self.metadata, "retrieval": retrieval},
        }


@dataclass
class RetrievalBatch:
    channel: str
    items: list[MemoryCandidate]
    health: dict[str, Any]
    latency_ms: float = 0.0


@dataclass(frozen=True)
class HybridFusionConfig:
    mode: str = "weighted_rrf"
    rrf_k: int = 60
    channel_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_CHANNEL_WEIGHTS)
    )
    rrf_weight: float = 0.50
    relevance_weight: float = 0.20
    authority_weight: float = 0.15
    confidence_weight: float = 0.10
    importance_weight: float = 0.05

    def __post_init__(self) -> None:
        if self.mode not in {"baseline", "weighted_rrf"}:
            raise ValueError(f"unsupported hybrid fusion mode: {self.mode}")
        if self.rrf_k < 1:
            raise ValueError("rrf_k must be positive")


class LexicalRetriever(Protocol):
    def retrieve_lexical(
        self, *, query: str, scope: RetrievalScope, limit: int
    ) -> RetrievalBatch: ...


class VectorRetriever(Protocol):
    def retrieve_vector(
        self, *, query: str, scope: RetrievalScope, limit: int
    ) -> RetrievalBatch: ...


class GraphRetriever(Protocol):
    def retrieve_graph(
        self, *, query: str, scope: RetrievalScope, limit: int
    ) -> RetrievalBatch: ...


def retrieval_channel_for(source_id: str, item_type: str) -> str:
    if source_id == "source-graph-memory" or item_type == "graph_memory":
        return "graph"
    if source_id == "source-approved-memory-vector":
        return "vector"
    if source_id in {"source-obsidian", "source-openclaw-memory"}:
        return "lexical"
    if source_id == "source-approved-memory":
        return "lexical"
    return "structured"


def authority_score_for(source_id: str, item_type: str, metadata: dict[str, Any]) -> float:
    if item_type in {"profile", "profile_fact"}:
        return 1.0
    if source_id in {"source-approved-memory", "source-approved-memory-vector"}:
        return 0.98 if str(metadata.get("project_id") or "") else 0.95
    if item_type == "project":
        return 0.96
    if source_id == "source-graph-memory":
        return 0.85 if metadata.get("authority") in {"approved_memory", "approved_projection"} else 0.65
    if source_id == "source-obsidian":
        return 0.78
    if source_id == "source-openclaw-memory":
        return 0.60
    return 0.70


def context_item(
    *,
    item_type: str,
    source_id: str,
    source_ref: str,
    title: str,
    content: str,
    score: float,
    confidence: float,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a legacy-compatible Context Pack item with the v1 contract."""
    item_metadata = dict(metadata or {})
    channel = retrieval_channel_for(source_id, item_type)
    raw_graph_score = item_metadata.get("graph_score")
    channel_score = raw_graph_score if channel == "graph" and raw_graph_score is not None else score
    scope = RetrievalScope(
        user_id=str(item_metadata.get("user_id") or item_metadata.get("owner_user_id") or ""),
        project_id=str(item_metadata.get("project_id") or ""),
        agent_id=str(item_metadata.get("agent_id") or ""),
        visibility=str(item_metadata.get("visibility") or ("project" if item_metadata.get("project_id") else "private")),
    )
    candidate = MemoryCandidate(
        source_type=item_type,
        source_id=source_id,
        source_ref=str(source_ref or ""),
        title=str(title or source_ref),
        content=str(content or ""),
        final_score=score,
        confidence=confidence,
        channel=channel,
        scope=scope,
        channel_scores={channel: channel_score},
        authority_score=authority_score_for(source_id, item_type, item_metadata),
        importance=str(item_metadata.get("importance") or "normal"),
        status=str(item_metadata.get("status") or "active"),
        updated_at=item_metadata.get("updated_at") or item_metadata.get("freshness_at"),
        metadata=item_metadata,
    )
    return candidate.to_context_item()


def _retrieval_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    retrieval = metadata.get("retrieval") if isinstance(metadata.get("retrieval"), dict) else {}
    return retrieval


def _candidate_key(item: dict[str, Any]) -> str:
    source_ref = str(item.get("source_ref") or "").strip()
    if source_ref:
        return source_ref
    retrieval = _retrieval_metadata(item)
    return str(retrieval.get("content_hash") or _stable_hash(item.get("content") or ""))


def rank_hybrid_items(
    items: list[dict[str, Any]],
    *,
    config: HybridFusionConfig | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deduplicate and rank incomparable retrieval channels with weighted RRF.

    RRF consumes only within-channel rank, so lexical, vector and graph scores
    do not need the same calibration.  A bounded policy layer then incorporates
    authority, confidence and importance without replacing relevance.
    """
    fusion = config or HybridFusionConfig()
    candidates = [copy.deepcopy(item) for item in items if item.get("content")]
    by_channel: dict[str, list[dict[str, Any]]] = {
        channel: [] for channel in RETRIEVAL_CHANNEL_ORDER
    }
    for item in candidates:
        channel = str(_retrieval_metadata(item).get("primary_channel") or "")
        if channel in by_channel:
            by_channel[channel].append(item)

    channel_ranks: dict[str, dict[str, int]] = {}
    active_channels: list[str] = []
    for channel in RETRIEVAL_CHANNEL_ORDER:
        ordered = sorted(
            by_channel[channel],
            key=lambda item: (
                -float(item.get("score") or 0),
                str(item.get("title") or ""),
                _candidate_key(item),
            ),
        )
        seen: set[str] = set()
        for item in ordered:
            key = _candidate_key(item)
            if key in seen:
                continue
            seen.add(key)
            channel_ranks.setdefault(key, {})[channel] = len(seen)
        if seen:
            active_channels.append(channel)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in candidates:
        grouped.setdefault(_candidate_key(item), []).append(item)

    maximum_rrf = sum(
        max(float(fusion.channel_weights.get(channel, 1.0)), 0.0)
        / (fusion.rrf_k + 1)
        for channel in active_channels
    ) or 1.0
    ranked: list[dict[str, Any]] = []
    for key, members in grouped.items():
        members.sort(
            key=lambda item: (
                -float(item.get("score") or 0),
                -float(_retrieval_metadata(item).get("authority_score") or 0),
                str(item.get("title") or ""),
            )
        )
        winner = copy.deepcopy(members[0])
        winner_metadata = (
            dict(winner.get("metadata") or {})
            if isinstance(winner.get("metadata"), dict)
            else {}
        )
        winner_retrieval = dict(_retrieval_metadata(winner))
        raw_scores: dict[str, float] = {}
        channels: set[str] = set()
        authority = 0.0
        confidence = 0.0
        importance = "low"
        importance_score = 0.0
        original_best_score = 0.0
        for member in members:
            retrieval = _retrieval_metadata(member)
            channel = str(retrieval.get("primary_channel") or "")
            member_scores = retrieval.get("scores") if isinstance(retrieval.get("scores"), dict) else {}
            if channel in RETRIEVAL_CHANNELS:
                channels.add(channel)
                raw_scores[channel] = max(
                    raw_scores.get(channel, 0.0),
                    float(member_scores.get(channel, member.get("score") or 0)),
                )
            for listed in retrieval.get("channels") or []:
                if listed in RETRIEVAL_CHANNELS:
                    channels.add(listed)
            authority = max(authority, float(retrieval.get("authority_score") or 0))
            confidence = max(confidence, float(member.get("confidence") or 0))
            member_importance = str(retrieval.get("importance") or "normal")
            member_importance_score = IMPORTANCE_WEIGHTS.get(member_importance, 0.65)
            if member_importance_score > importance_score:
                importance = member_importance
                importance_score = member_importance_score
            original_best_score = max(original_best_score, float(member.get("score") or 0))

        ranks = channel_ranks.get(key, {})
        contributions = {
            channel: round(
                max(float(fusion.channel_weights.get(channel, 1.0)), 0.0)
                / (fusion.rrf_k + rank),
                8,
            )
            for channel, rank in ranks.items()
        }
        normalized_rrf = min(sum(contributions.values()) / maximum_rrf, 1.0)
        if fusion.mode == "baseline":
            final_score = original_best_score
            strategy = "score-sort-baseline"
        else:
            final_score = (
                fusion.rrf_weight * normalized_rrf
                + fusion.relevance_weight * original_best_score
                + fusion.authority_weight * authority
                + fusion.confidence_weight * confidence
                + fusion.importance_weight * importance_score
            )
            strategy = HYBRID_FUSION_VERSION
        final_score = _clamp(final_score)
        winner["score"] = final_score
        winner["confidence"] = _clamp(confidence, 1.0)
        winner["metadata"] = {
            **winner_metadata,
            "retrieval": {
                **winner_retrieval,
                "channels": sorted(channels),
                "scores": {**raw_scores, "final": final_score},
                "authority_score": _clamp(authority),
                "importance": importance,
                "fusion": {
                    "version": HYBRID_FUSION_VERSION,
                    "strategy": strategy,
                    "rrf_k": fusion.rrf_k,
                    "channel_ranks": ranks,
                    "channel_contributions": contributions,
                    "rrf_score": round(normalized_rrf, 6),
                    "original_best_score": _clamp(original_best_score),
                    "policy_features": {
                        "authority": _clamp(authority),
                        "confidence": _clamp(confidence),
                        "importance": _clamp(importance_score),
                    },
                },
            },
        }
        ranked.append(winner)

    ranked.sort(
        key=lambda item: (
            -float(item.get("score") or 0),
            -float(_retrieval_metadata(item).get("authority_score") or 0),
            str(item.get("title") or ""),
            _candidate_key(item),
        )
    )
    diagnostics = {
        "version": HYBRID_FUSION_VERSION,
        "mode": fusion.mode,
        "strategy": HYBRID_FUSION_VERSION if fusion.mode == "weighted_rrf" else "score-sort-baseline",
        "rrf_k": fusion.rrf_k,
        "channel_weights": {
            channel: float(fusion.channel_weights.get(channel, 1.0))
            for channel in RETRIEVAL_CHANNEL_ORDER
        },
        "active_channels": active_channels,
        "input_candidates": len(candidates),
        "deduplicated_candidates": len(ranked),
        "multi_channel_candidates": sum(
            1 for item in ranked if len(_retrieval_metadata(item).get("channels") or []) > 1
        ),
        "reranker": "authority-confidence-importance-policy.v1" if fusion.mode == "weighted_rrf" else "disabled",
    }
    return ranked, diagnostics


def compare_rankings(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    *,
    k: int = 10,
) -> dict[str, Any]:
    cutoff = max(1, int(k))
    baseline_refs = [_candidate_key(item) for item in baseline[:cutoff]]
    candidate_refs = [_candidate_key(item) for item in candidate[:cutoff]]
    baseline_set = set(baseline_refs)
    candidate_set = set(candidate_refs)
    common = baseline_set & candidate_set
    displacement = [
        abs(baseline_refs.index(ref) - candidate_refs.index(ref))
        for ref in common
    ]
    return {
        "k": cutoff,
        "overlap": len(common),
        "overlap_ratio": round(len(common) / max(len(baseline_set | candidate_set), 1), 4),
        "top1_changed": (baseline_refs[:1] != candidate_refs[:1]),
        "mean_rank_displacement": round(sum(displacement) / max(len(displacement), 1), 4),
        "baseline_refs": baseline_refs,
        "candidate_refs": candidate_refs,
    }


def build_retrieval_strategy(
    health: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    fusion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe what actually ran; absence of vectors is explicit, not hidden."""
    channel_counts = {channel: 0 for channel in RETRIEVAL_CHANNEL_ORDER}
    for item in items:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        retrieval = metadata.get("retrieval") if isinstance(metadata.get("retrieval"), dict) else {}
        channels = retrieval.get("channels") if isinstance(retrieval.get("channels"), list) else []
        if not channels:
            channels = [str(retrieval.get("primary_channel") or "")]
        for channel in set(channels):
            if channel in channel_counts:
                channel_counts[channel] += 1

    graph_health = health.get("graph_memory") if isinstance(health.get("graph_memory"), dict) else {}
    vector_health = health.get("vector_memory") if isinstance(health.get("vector_memory"), dict) else {}
    fusion_health = fusion or (
        health.get("hybrid_fusion") if isinstance(health.get("hybrid_fusion"), dict) else {}
    )
    active = [channel for channel in RETRIEVAL_CHANNEL_ORDER if channel_counts[channel]]
    mode = "+".join(active) if active else "empty"
    return {
        "version": RETRIEVAL_STRATEGY_VERSION,
        "mode": mode,
        "fusion": str(fusion_health.get("strategy") or "score-sort-baseline"),
        "fusion_version": fusion_health.get("version"),
        "fusion_rollout_mode": str(fusion_health.get("rollout_mode") or "baseline"),
        "reranker": str(
            fusion_health.get("reranker")
            or ("graph-policy-only" if graph_health.get("evaluation_mode") == "rerank" else "disabled")
        ),
        "channels": {
            "structured": {"status": "ready", "selected": channel_counts["structured"]},
            "lexical": {"status": "ready", "selected": channel_counts["lexical"]},
            "vector": {
                "status": str(vector_health.get("status") or "not_configured"),
                "selected": channel_counts["vector"],
            },
            "graph": {
                "status": str(graph_health.get("status") or "disabled"),
                "selected": channel_counts["graph"],
            },
        },
    }


def evaluate_retrieval_cases(
    cases: list[dict[str, Any]],
    retrieve: Callable[[dict[str, Any]], list[str]],
    *,
    k: int = 10,
) -> dict[str, Any]:
    """Small deterministic baseline evaluator used before vector rollout."""
    evaluated = positive_cases = hits = reciprocal_rank_total = forbidden_hits = 0
    relevant_returned = relevant_expected = ndcg_total = 0.0
    details: list[dict[str, Any]] = []
    for case in cases:
        expected = {str(item) for item in case.get("expected_source_refs") or []}
        forbidden = {str(item) for item in case.get("forbidden_source_refs") or []}
        if not expected and not forbidden:
            continue
        refs = [str(item) for item in retrieve(case)[: max(1, int(k))]]
        first_rank = next((index for index, ref in enumerate(refs, start=1) if ref in expected), None)
        hit = bool(first_rank) if expected else True
        forbidden_count = sum(1 for ref in refs if ref in forbidden)
        evaluated += 1
        if expected:
            positive_cases += 1
            hits += int(hit)
            reciprocal_rank_total += 1.0 / first_rank if first_rank else 0.0
            relevant_positions = [
                index for index, ref in enumerate(refs, start=1) if ref in expected
            ]
            relevant_returned += len(relevant_positions)
            relevant_expected += len(expected)
            dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_positions)
            ideal_count = min(len(expected), max(1, int(k)))
            idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
            ndcg_total += dcg / idcg if idcg else 0.0
        forbidden_hits += forbidden_count
        details.append(
            {
                "id": str(case.get("id") or f"case-{evaluated}"),
                "hit": hit,
                "first_relevant_rank": first_rank,
                "relevant_returned": sum(1 for ref in refs if ref in expected),
                "forbidden_hits": forbidden_count,
                "returned": refs,
            }
        )
    positive_denominator = max(positive_cases, 1)
    return {
        "cases": evaluated,
        "positive_cases": positive_cases,
        "recall_at_k": round(hits / positive_denominator, 4),
        "item_recall_at_k": round(relevant_returned / max(relevant_expected, 1), 4),
        "mrr_at_k": round(reciprocal_rank_total / positive_denominator, 4),
        "ndcg_at_k": round(ndcg_total / positive_denominator, 4),
        "forbidden_hits": forbidden_hits,
        "details": details,
    }


def assess_retrieval_rollout(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    max_recall_drop: float = 0.0,
    max_mrr_drop: float = 0.02,
) -> dict[str, Any]:
    """Apply a conservative rollout gate to offline retrieval metrics."""
    metrics = ("recall_at_k", "item_recall_at_k", "mrr_at_k", "ndcg_at_k")
    deltas = {
        metric: round(float(candidate.get(metric) or 0) - float(baseline.get(metric) or 0), 4)
        for metric in metrics
    }
    checks = {
        "forbidden_hits_non_increasing": int(candidate.get("forbidden_hits") or 0)
        <= int(baseline.get("forbidden_hits") or 0),
        "recall_within_budget": deltas["recall_at_k"] >= -abs(float(max_recall_drop)),
        "item_recall_within_budget": deltas["item_recall_at_k"] >= -abs(float(max_recall_drop)),
        "mrr_within_budget": deltas["mrr_at_k"] >= -abs(float(max_mrr_drop)),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "deltas": deltas,
        "baseline": {metric: baseline.get(metric) for metric in metrics},
        "candidate": {metric: candidate.get(metric) for metric in metrics},
    }
