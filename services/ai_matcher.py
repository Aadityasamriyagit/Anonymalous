from __future__ import annotations

import math
from typing import Any

import google.generativeai as genai

from config import Settings


class AIMatcherService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        genai.configure(api_key=settings.gemini_api_key)
        self._moderation_model = genai.GenerativeModel(settings.gemini_moderation_model)

    async def embed_bio(self, bio: str) -> list[float]:
        # Embedding is called synchronously by the SDK internally; we keep this async to fit bot pipelines.
        result = genai.embed_content(
            model=self.settings.gemini_embed_model,
            content=bio,
            task_type='semantic_similarity',
        )
        return result['embedding']

    async def moderation_check(self, text: str) -> tuple[bool, float, str]:
        prompt = (
            'Classify this message for anonymous chat safety. '
            'Return JSON with keys: toxic(boolean), score(0..1), reason(short). '
            f'Message: {text!r}'
        )
        response = await self._moderation_model.generate_content_async(prompt)
        raw = response.text or '{}'
        try:
            import json

            parsed = json.loads(raw.strip('`\n '))
            toxic = bool(parsed.get('toxic', False))
            score = float(parsed.get('score', 0.0))
            reason = str(parsed.get('reason', ''))
            return toxic, score, reason
        except Exception:
            lowered = raw.lower()
            toxic = any(k in lowered for k in ('toxic', 'harass', 'abuse', 'hate'))
            return toxic, 0.5 if toxic else 0.0, 'Fallback moderation parser'

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        # Cosine similarity gives a robust angle-based semantic compatibility score for text embeddings.
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if not norm1 or not norm2:
            return 0.0
        return dot / (norm1 * norm2)

    async def best_candidates(
        self,
        my_embedding: list[float],
        candidates: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        scored = []
        for candidate in candidates:
            other_emb = candidate.get('bio_embedding') or []
            score = self.cosine_similarity(my_embedding, other_emb)
            scored.append((score, candidate))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [{**cand, 'compatibility_score': round(score * 100, 2)} for score, cand in scored[:top_k]]
