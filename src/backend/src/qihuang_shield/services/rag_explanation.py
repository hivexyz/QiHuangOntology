from __future__ import annotations

import json
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from ..config import Settings
from .vector_search import VectorSearchService


RAG_EXPLANATION_PROMPT_VERSION = "rag-explanation-v1"


class RagExplanationService:
    def __init__(self, settings: Settings, vector_search_service: VectorSearchService | None = None) -> None:
        self._settings = settings
        self._vector_search_service = vector_search_service

    def build_explanation(
        self,
        *,
        content_text: str,
        decision: str,
        risk_level: str,
        matches: list[Any],
        scenario: str,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        evidence_pack: list[dict[str, Any]] = []
        retrieval_meta: dict[str, Any] | None = None
        query = self._build_query(content_text=content_text, matches=matches, scenario=scenario)

        if self._vector_search_service is not None:
            try:
                retrieval = self._vector_search_service.rag_search(query=query, top_k=3)
                evidence_pack = retrieval.get("evidence_pack", []) or []
                retrieval_meta = {
                    "query": retrieval.get("query"),
                    "top_k": retrieval.get("top_k"),
                    "embedding_model": retrieval.get("embedding_model"),
                    "hit_count": len(retrieval.get("hits", []) or []),
                }
            except Exception as exc:
                retrieval_meta = {"query": query, "error": str(exc), "hit_count": 0}

        llm_used = False
        fallback_reason = None
        explanation = None
        if self._llm_ready():
            try:
                explanation = self._generate_with_llm(
                    content_text=content_text,
                    decision=decision,
                    risk_level=risk_level,
                    matches=matches,
                    scenario=scenario,
                    evidence_pack=evidence_pack,
                )
                llm_used = True
            except Exception as exc:
                fallback_reason = str(exc)

        if not explanation:
            explanation = self._compose_template_explanation(
                decision=decision,
                risk_level=risk_level,
                matches=matches,
                evidence_pack=evidence_pack,
            )

        meta = {
            **(retrieval_meta or {}),
            "llm_used": llm_used,
            "fallback_reason": fallback_reason,
            "prompt_version": RAG_EXPLANATION_PROMPT_VERSION,
            "evidence_count": len(evidence_pack),
        }
        return explanation, evidence_pack, meta

    def _llm_ready(self) -> bool:
        return bool(self._settings.llm_ready)

    def _generate_with_llm(
        self,
        *,
        content_text: str,
        decision: str,
        risk_level: str,
        matches: list[Any],
        scenario: str,
        evidence_pack: list[dict[str, Any]],
    ) -> str:
        payload = self._build_llm_payload(
            content_text=content_text,
            decision=decision,
            risk_level=risk_level,
            matches=matches,
            scenario=scenario,
            evidence_pack=evidence_pack,
        )
        response_data = self._post_json(payload)
        text = self._extract_text_response(response_data)
        cleaned = text.strip()
        if not cleaned:
            raise RuntimeError("LLM explanation is empty")
        return cleaned

    def _build_llm_payload(
        self,
        *,
        content_text: str,
        decision: str,
        risk_level: str,
        matches: list[Any],
        scenario: str,
        evidence_pack: list[dict[str, Any]],
    ) -> dict[str, Any]:
        rules = []
        reasons = []
        for match in matches:
            rule_name = getattr(match, "rule_name", None)
            if rule_name and rule_name not in rules:
                rules.append(str(rule_name))
            reason = getattr(match, "reason", None)
            if reason and reason not in reasons:
                reasons.append(str(reason))

        evidence_briefs = []
        for item in evidence_pack[:3]:
            evidence_briefs.append(
                {
                    "asset_type": (
                        item.get("projection_asset_type")
                        or item.get("metadata", {}).get("projection_asset_type")
                        or item.get("asset_type")
                        or item.get("metadata", {}).get("asset_type")
                    ),
                    "text": (item.get("text") or "")[:160],
                    "metadata": item.get("metadata", {}),
                }
            )

        system_prompt = (
            "你是内容审核解释助手。"
            "请基于已命中的规则与检索证据，生成一段简洁、可解释、面向审核员的风险说明。"
            "不要编造证据中没有的信息。"
            "输出自然语言，不要输出 Markdown，不要分点。"
        )
        user_payload = {
            "content_text": content_text,
            "scenario": scenario,
            "decision": decision,
            "risk_level": risk_level,
            "matched_rules": rules,
            "matched_reasons": reasons,
            "evidence": evidence_briefs,
            "style": "请输出 2-4 句中文解释，包含风险判断、命中原因、与证据关联。",
        }
        return {
            "model": self._settings.llm_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = self._settings.llm_base_url.rstrip("/")
        endpoint = self._settings.llm_endpoint.strip()
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        url = f"{base_url}{endpoint}"
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._settings.llm_api_key}",
            },
        )
        try:
            with request.urlopen(req, timeout=self._settings.llm_timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:300]}") from exc
        except URLError as exc:
            raise RuntimeError(f"LLM connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("LLM request timed out") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM response is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("LLM response root is not an object")
        return parsed

    def _extract_text_response(self, response_data: dict[str, Any]) -> str:
        for choice in response_data.get("choices", []) or []:
            message = choice.get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = [item.get("text") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
                if texts:
                    return "\n".join(texts)
        output = response_data.get("output") or []
        for item in output:
            for content in item.get("content", []) or []:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    return content["text"]
        raise RuntimeError("Unable to extract text from LLM response")

    def _build_query(self, *, content_text: str, matches: list[Any], scenario: str) -> str:
        rule_names = []
        entity_names = []
        for match in matches:
            rule_name = getattr(match, "rule_name", None)
            if rule_name and rule_name not in rule_names:
                rule_names.append(str(rule_name))
            for entity in getattr(match, "matched_entities", []) or []:
                standard_name = entity.get("standard_name") or entity.get("name")
                if standard_name and standard_name not in entity_names:
                    entity_names.append(str(standard_name))
        parts = [content_text.strip()]
        if scenario:
            parts.append(f"场景:{scenario}")
        if entity_names:
            parts.append("实体:" + "、".join(entity_names[:5]))
        if rule_names:
            parts.append("规则:" + "、".join(rule_names[:5]))
        return " | ".join(part for part in parts if part)

    def _compose_template_explanation(
        self,
        *,
        decision: str,
        risk_level: str,
        matches: list[Any],
        evidence_pack: list[dict[str, Any]],
    ) -> str:
        reasons = [getattr(match, "reason", "") for match in matches if getattr(match, "reason", "")]
        rules = [getattr(match, "rule_name", "") for match in matches if getattr(match, "rule_name", "")]
        unique_rules = []
        for rule in rules:
            if rule not in unique_rules:
                unique_rules.append(rule)
        evidence_lines = []
        for item in evidence_pack[:2]:
            text = (item.get("text") or "").strip().replace("\n", "；")
            asset_type = (
                item.get("projection_asset_type")
                or item.get("metadata", {}).get("projection_asset_type")
                or item.get("asset_type")
                or item.get("metadata", {}).get("asset_type")
                or "evidence"
            )
            if text:
                evidence_lines.append(f"[{asset_type}] {text[:120]}")

        if decision == "block":
            lead = "内容命中高风险规则，建议拦截或人工二次确认。"
        elif decision == "review":
            lead = "内容存在中高风险知识信号，建议进入人工复核。"
        else:
            lead = "内容未命中显著高风险规则，可通过。"

        parts = [lead]
        if unique_rules:
            parts.append("命中规则：" + "、".join(unique_rules[:3]) + "。")
        if reasons:
            parts.append("判定依据：" + "；".join(reasons[:3]) + "。")
        if evidence_lines:
            parts.append("检索证据：" + "；".join(evidence_lines) + "。")
        parts.append(f"综合风险等级：{risk_level}。")
        return "".join(parts)
