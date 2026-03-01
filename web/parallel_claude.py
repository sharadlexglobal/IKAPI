"""
Async parallel Claude API calls using anthropic.AsyncAnthropic.
Enables concurrent requests to Claude Sonnet 4.6 via asyncio.gather.
"""
import asyncio
import json
import logging
import os
import time
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


def _strip_markdown_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    return text


def _extract_usage(message) -> dict:
    if hasattr(message, "usage"):
        return {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
        }
    return {}


async def _call_claude_async(
    client: anthropic.AsyncAnthropic,
    *,
    model: str,
    system: str,
    user_message: str,
    max_tokens: int = 16000,
    timeout: int = 300,
    task_id: str = "",
    parse_json: bool = True,
) -> dict[str, Any]:
    start = time.time()
    try:
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            timeout=timeout,
        )
        elapsed = round(time.time() - start, 2)
        response_text = message.content[0].text.strip()

        result = {
            "task_id": task_id,
            "success": True,
            "elapsed_seconds": elapsed,
            "usage": _extract_usage(message),
        }

        if parse_json:
            cleaned = _strip_markdown_json(response_text)
            result["data"] = json.loads(cleaned)
        else:
            result["data"] = response_text

        logger.info(f"[parallel_claude] Task '{task_id}' completed in {elapsed}s")
        return result

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        logger.error(f"[parallel_claude] Task '{task_id}' failed after {elapsed}s: {e}")
        return {
            "task_id": task_id,
            "success": False,
            "elapsed_seconds": elapsed,
            "error": str(e),
        }


async def run_parallel_calls(
    calls: list[dict],
    api_key: str | None = None,
    model: str | None = None,
    max_concurrency: int = 6,
) -> list[dict[str, Any]]:
    """
    Execute multiple Claude API calls in parallel.

    Args:
        calls: List of dicts, each with keys:
            - system: str (system prompt)
            - user_message: str
            - task_id: str (identifier for tracking)
            - max_tokens: int (optional, default 16000)
            - parse_json: bool (optional, default True)
        api_key: Anthropic API key (falls back to env var)
        model: Model name (falls back to env var or claude-sonnet-4-6)
        max_concurrency: Max concurrent requests (default 6)

    Returns:
        List of result dicts with task_id, success, elapsed_seconds, data/error
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    semaphore = asyncio.Semaphore(max_concurrency)

    async def bounded_call(call_spec):
        async with semaphore:
            return await _call_claude_async(
                client,
                model=model,
                system=call_spec["system"],
                user_message=call_spec["user_message"],
                max_tokens=call_spec.get("max_tokens", 16000),
                timeout=call_spec.get("timeout", 300),
                task_id=call_spec.get("task_id", ""),
                parse_json=call_spec.get("parse_json", True),
            )

    try:
        total_start = time.time()
        results = await asyncio.gather(*[bounded_call(c) for c in calls])
        total_elapsed = round(time.time() - total_start, 2)
    finally:
        await client.close()

    succeeded = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    logger.info(
        f"[parallel_claude] Batch complete: {succeeded} succeeded, {failed} failed, "
        f"total wall-clock: {total_elapsed}s"
    )

    return list(results)


def run_parallel_sync(calls: list[dict], **kwargs) -> list[dict[str, Any]]:
    """
    Synchronous wrapper around run_parallel_calls.
    Safe to call from non-async code (Flask routes, scripts, etc).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, run_parallel_calls(calls, **kwargs))
            return future.result()
    else:
        return asyncio.run(run_parallel_calls(calls, **kwargs))
