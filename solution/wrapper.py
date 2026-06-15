from __future__ import annotations

import hashlib
import json
import re
import time

from telemetry.logger import logger, new_correlation_id, set_correlation_id
from telemetry.cost import cost_from_usage
from telemetry.redact import redact

_NOTE_PAT = re.compile(r"(?is)\b(GHI\s*CHU|GHI\s*CHÚ|NOTE|NOTES)\s*[:：].*$")
_ROLELINE_PAT = re.compile(r"(?im)^\s*(system|developer|assistant)\s*:\s*.*$")


def _sanitize_question(q: str) -> str:
    if not isinstance(q, str):
        return q
    q2 = _NOTE_PAT.sub("", q).strip()
    q2 = _ROLELINE_PAT.sub("", q2).strip()
    return q2


def _cache_key(question: str, config: dict) -> str:
    h = hashlib.sha256()
    h.update(question.encode("utf-8"))
    h.update(str(config.get("model", "")).encode("utf-8"))
    h.update(str(config.get("temperature", "")).encode("utf-8"))
    return h.hexdigest()


def mitigate(call_next, question, config, context):
    cid = new_correlation_id()
    set_correlation_id(cid)

    qid = context.get("qid")
    sanitized = _sanitize_question(question)

    # --- cache ---
    if config.get("cache", {}).get("enabled"):
        key = _cache_key(sanitized, config)
        lock = context.get("cache_lock")
        cache = context.get("cache")
        if lock and cache is not None:
            with lock:
                hit = cache.get(key)
            if hit is not None:
                logger.log_event("CACHE_HIT", {"qid": qid})
                # return a copy (avoid accidental mutation)
                return json.loads(json.dumps(hit, ensure_ascii=False))

    def _call_once(conf: dict):
        t0 = time.time()
        res = call_next(sanitized, conf)
        wall_ms = int((time.time() - t0) * 1000)

        meta = res.get("meta", {}) or {}
        usage = meta.get("usage", {}) or {}
        ans = res.get("answer") or ""
        _, pii_n = redact(ans)

        logger.log_event("AGENT_CALL", {
            "qid": qid,
            "status": res.get("status"),
            "reported_latency_ms": meta.get("latency_ms"),
            "wall_ms": wall_ms,
            "tokens": usage,
            "cost_usd": cost_from_usage(meta.get("model", ""), usage),
            "tools_used": meta.get("tools_used", []),
            "pii_in_answer": pii_n > 0,
            "turn_index": meta.get("turn_index", context.get("turn_index")),
            "session_id": meta.get("session_id", context.get("session_id")),
        })
        return res

    try:
        # --- first call ---
        res = _call_once(config)

        # --- retry once if not ok ---
        if res.get("status") != "ok" and config.get("retry", {}).get("enabled"):
            time.sleep((config.get("retry", {}) or {}).get("backoff_ms", 0) / 1000.0)
            res = _call_once(config)

        # --- optional output redaction ---
        if config.get("redact_pii") and isinstance(res.get("answer"), str):
            redacted_text, _ = redact(res["answer"])
            res["answer"] = redacted_text

        # --- save cache ---
        if config.get("cache", {}).get("enabled"):
            key = _cache_key(sanitized, config)
            lock = context.get("cache_lock")
            cache = context.get("cache")
            if lock and cache is not None:
                with lock:
                    cache[key] = res

        return res

    except Exception as e:
        logger.log_event("WRAPPER_ERROR", {"qid": qid, "error": str(e)})
        return {
            "answer": None,
            "status": "wrapper_error",
            "steps": 0,
            "trace": [],
            "meta": {"latency_ms": 0, "usage": {}, "tools_used": []}
        }