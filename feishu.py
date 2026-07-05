"""Feishu message parsing and reply helpers.

Keeps the event-handler in main.py focused on routing.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Tuple

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

log = logging.getLogger(__name__)

# Per Feishu docs: text message bodies max out around 4000 chars. Leave headroom.
_MAX_TEXT_LEN = 3500


def _open_id(sender) -> Optional[str]:
    """Pull the open_id from a sender payload (UserId type)."""
    if sender is None:
        return None
    sid = getattr(sender, "sender_id", None)
    if sid is None:
        return None
    return getattr(sid, "open_id", None)


def _strip_at_mentions(text: str, mentions) -> str:
    """Replace @xxx tokens with the bot's display name so the LLM sees clean input.

    Feishu prefixes mentioned users with @ and embeds them in plain text;
    we just drop those prefixes here.
    """
    if not mentions:
        return text
    for m in mentions:
        # ``key`` looks like ``@_user_1`` — strip that token from the text.
        key = getattr(m, "key", None)
        if not key:
            continue
        # Also pull the friendly name out so we can show the LLM who was mentioned.
        name = getattr(m, "name", None) or key
        text = text.replace(key, f"@{name}")
    return text.strip()


def extract_text(event) -> Optional[Tuple[str, str, str, str, str]]:
    """Parse an incoming P2ImMessageReceiveV1 event.

    Returns (chat_id, message_id, sender_open_id, chat_type, text) when the
    event is a ``text`` message we should respond to. Returns None otherwise
    (non-text messages, group messages that don't @ the bot, etc.).
    """
    msg = event.event.message
    sender = event.event.sender
    if msg is None:
        return None

    # chat_type: "p2p" (direct) or "group"
    chat_type = msg.chat_type or ""
    if msg.message_type != "text":
        log.info("skip non-text message: type=%s", msg.message_type)
        return None

    # Group messages: only respond when the bot is @-mentioned.
    if chat_type == "group":
        mentions = msg.mentions or []
        bot_mentioned = any(
            (getattr(m, "id_type", None) == "open_id"
             and getattr(m.id, "open_id", None) is not None)
            for m in mentions
        ) if mentions else False
        if not bot_mentioned:
            log.info("skip group message without @bot")
            return None
    elif chat_type != "p2p":
        log.info("skip message with chat_type=%s", chat_type)
        return None

    try:
        payload = json.loads(msg.content or "{}")
    except json.JSONDecodeError:
        log.warning("failed to parse message content: %r", msg.content)
        return None
    text = (payload.get("text") or "").strip()
    if not text:
        return None

    # For group messages, drop the leading @bot token so the LLM sees clean input.
    if chat_type == "group":
        text = _strip_at_mentions(text, msg.mentions or [])

    sender_open_id = _open_id(sender) or ""
    return msg.chat_id, msg.message_id, sender_open_id, chat_type, text


def session_key_for(chat_type: str, chat_id: str, sender_open_id: str) -> str:
    """Build a stable session key. p2p uses sender; group uses chat+user so
    different users in the same group don't share history."""
    if chat_type == "p2p":
        return f"p2p:{sender_open_id}"
    return f"group:{chat_id}:{sender_open_id}"


def _truncate(text: str) -> str:
    if len(text) <= _MAX_TEXT_LEN:
        return text
    return text[:_MAX_TEXT_LEN] + "\n…(回复过长，已截断)"


def reply_text(client: lark.Client, message_id: str, text: str) -> None:
    """Reply to a specific message with a plain text body."""
    body = (
        ReplyMessageRequestBody.builder()
        .msg_type("text")
        .content(json.dumps({"text": _truncate(text)}, ensure_ascii=False))
        .build()
    )
    req = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(body)
        .build()
    )
    resp = client.im.v1.message.reply(req)
    if not resp.success():
        log.error("reply failed code=%s msg=%s", resp.code, resp.msg)
    else:
        log.info("reply ok message_id=%s", message_id)


def send_text(client: lark.Client, receive_id: str, receive_id_type: str, text: str) -> None:
    """Send a fresh message (not a reply). receive_id_type: 'open_id' | 'chat_id'."""
    body = (
        CreateMessageRequestBody.builder()
        .receive_id(receive_id)
        .msg_type("text")
        .content(json.dumps({"text": _truncate(text)}, ensure_ascii=False))
        .build()
    )
    req = (
        CreateMessageRequest.builder()
        .receive_id_type(receive_id_type)
        .request_body(body)
        .build()
    )
    resp = client.im.v1.message.create(req)
    if not resp.success():
        log.error("send failed code=%s msg=%s", resp.code, resp.msg)


def reply_card(client: lark.Client, message_id: str, title: str, content: str, 
               template: str = "blue", img_key: Optional[str] = None) -> None:
    """Reply to a specific message with an interactive card.
    
    Args:
        title: Card header title
        content: Markdown content for the card body
        template: Header color template (blue, green, red, etc.)
        img_key: Optional image key to include at the top
    """
    elements = []
    
    # Optional image at the top
    if img_key:
        elements.append({
            "tag": "img",
            "img_key": img_key,
            "corner_radius": "8px",
            "margin": "0px"
        })
    
    # Interactive container with markdown content
    elements.append({
        "tag": "interactive_container",
        "border_color": template,
        "corner_radius": "8px",
        "elements": [
            {
                "tag": "markdown",
                "content": _truncate(content)
            }
        ],
        "has_border": True,
        "margin": "0px",
        "padding": "12px"
    })
    
    card_payload = {
        "schema": "2.0",
        "header": {
            "title": {
                "tag": "plain_text",
                "content": title
            },
            "template": template,
            "padding": "12px 8px 12px 8px"
        },
        "body": {
            "elements": elements
        }
    }
    
    body = (
        ReplyMessageRequestBody.builder()
        .msg_type("interactive")
        .content(json.dumps(card_payload, ensure_ascii=False))
        .build()
    )
    req = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(body)
        .build()
    )
    resp = client.im.v1.message.reply(req)
    if not resp.success():
        log.error("reply card failed code=%s msg=%s", resp.code, resp.msg)
    else:
        log.info("reply card ok message_id=%s", message_id)


def send_card(client: lark.Client, receive_id: str, receive_id_type: str,
              title: str, content: str, template: str = "blue", 
              img_key: Optional[str] = None) -> None:
    """Send a fresh card message (not a reply)."""
    elements = []
    
    if img_key:
        elements.append({
            "tag": "img",
            "img_key": img_key,
            "corner_radius": "8px",
            "margin": "0px"
        })
    
    elements.append({
        "tag": "interactive_container",
        "border_color": template,
        "corner_radius": "8px",
        "elements": [
            {
                "tag": "markdown",
                "content": _truncate(content)
            }
        ],
        "has_border": True,
        "margin": "0px",
        "padding": "12px"
    })
    
    card_payload = {
        "schema": "2.0",
        "header": {
            "title": {
                "tag": "plain_text",
                "content": title
            },
            "template": template,
            "padding": "12px 8px 12px 8px"
        },
        "body": {
            "elements": elements
        }
    }
    
    body = (
        CreateMessageRequestBody.builder()
        .receive_id(receive_id)
        .msg_type("interactive")
        .content(json.dumps(card_payload, ensure_ascii=False))
        .build()
    )
    req = (
        CreateMessageRequest.builder()
        .receive_id_type(receive_id_type)
        .request_body(body)
        .build()
    )
    resp = client.im.v1.message.create(req)
    if not resp.success():
        log.error("send card failed code=%s msg=%s", resp.code, resp.msg)
