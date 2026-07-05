"""Feishu bot entry point: WS connection for events + REST client for replies.

Listens for incoming IM messages, hands them to the LLM agent, and replies
in the same conversation thread.
"""
import logging

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

import config
from agent import LLMError, LLMAgent
from feishu import extract_text, reply_card, session_key_for
from session import SessionStore

log = logging.getLogger(__name__)


# --- Agent + REST client (long-lived, reused for every event) ---------------

# REST client is separate from the WS client. It carries the tenant access
# token used to call /im/v1/messages/:id/reply.
_rest_client = (
    lark.Client.builder()
    .app_id(config.APP_ID)
    .app_secret(config.APP_SECRET)
    .log_level(lark.LogLevel.INFO)
    .build()
)

_sessions = SessionStore(max_turns=config.MAX_HISTORY_TURNS)
_agent = LLMAgent(_sessions)


# --- Event handlers ---------------------------------------------------------

def do_message_receive(data: P2ImMessageReceiveV1) -> None:
    parsed = extract_text(data)
    if parsed is None:
        return  # Non-text, non-@-mention, or empty message — silently ignore.

    chat_id, message_id, sender_open_id, chat_type, text = parsed
    key = session_key_for(chat_type, chat_id, sender_open_id)
    log.info("recv chat=%s sender=%s text=%r", chat_id, sender_open_id, text)

    try:
        reply = _agent.chat(key, text)
    except LLMError as e:
        log.exception("agent failed: %s", e)
        reply = f"抱歉，模型调用失败：{e}"

    try:
        # 使用卡片格式回复
        reply_card(
            _rest_client, 
            message_id, 
            title="🤖 AI Assistant",
            content=reply,
            template="blue"
        )
    except Exception:
        log.exception("failed to send reply message_id=%s", message_id)


# --- WS dispatcher wiring ---------------------------------------------------

event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_message_receive)
    .build()
)


def main() -> None:
    cli = lark.ws.Client(
        config.APP_ID,
        config.APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    log.info("starting feishu ws client, model=%s", config.LLM_MODEL)
    try:
        cli.start()
    finally:
        _agent.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
