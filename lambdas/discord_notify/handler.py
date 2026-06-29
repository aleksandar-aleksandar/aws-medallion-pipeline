"""Forward CloudWatch alarm notifications (via SNS) to a Discord webhook."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _format_alarm(message: dict[str, Any]) -> str:
    name = message.get("AlarmName", "unknown-alarm")
    reason = message.get("NewStateReason", "No reason provided")
    state = message.get("NewStateValue", "ALARM")
    time = message.get("StateChangeTime", "")

    function_name = ""
    trigger = message.get("Trigger", {})
    for dim in trigger.get("Dimensions", []):
        if not isinstance(dim, dict):
            continue
        dim_name = dim.get("name") or dim.get("Name")
        if dim_name == "FunctionName":
            function_name = dim.get("value") or dim.get("Value") or ""
            break

    lines = [
        f"**Pipeline alert: {state}**",
        f"**Alarm:** `{name}`",
    ]
    if function_name:
        lines.append(f"**Lambda:** `{function_name}`")
    if time:
        lines.append(f"**Time:** {time}")
    lines.append(f"**Reason:** {reason}")
    return "\n".join(lines)


def _post_discord(webhook_url: str, content: str) -> None:
    payload = json.dumps(
        {
            "username": "AWS Medallion Pipeline",
            "content": content[:1900],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "aws-medallion-pipeline/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        logger.info("Discord webhook response: %s", response.status)


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    event = event or {}
    webhook_url = _env("DISCORD_WEBHOOK_URL")
    sent = 0

    for record in event.get("Records", []):
        if record.get("EventSource") != "aws:sns":
            continue
        raw = record.get("Sns", {}).get("Message", "{}")
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            message = {"NewStateReason": str(raw), "AlarmName": "sns-message"}
        text = _format_alarm(message) if isinstance(message, dict) else str(message)
        _post_discord(webhook_url, text)
        sent += 1

    if sent == 0:
        _post_discord(webhook_url, f"**Pipeline alert**\n```{json.dumps(event)[:1800]}```")
        sent = 1

    return {"status": "ok", "messages_sent": sent}
