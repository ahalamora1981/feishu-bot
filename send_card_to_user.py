"""Send a test card message to a user via Feishu bot."""
import lark_oapi as lark

import config
from feishu import send_card


def main():
    client = (
        lark.Client.builder()
        .app_id(config.APP_ID)
        .app_secret(config.APP_SECRET)
        .log_level(lark.LogLevel.INFO)
        .build()
    )

    open_id = config._get("OPEN_ID")
    print(f"Sending card to open_id={open_id}")

    send_card(
        client,
        receive_id=open_id,
        receive_id_type="open_id",
        title="🧪 测试卡片",
        content="这是一条 **测试消息**，如果你看到了说明 `send_card` 工作正常。\n\n- 支持 Markdown\n- 支持粗体、列表\n- 支持 emoji 🎉",
        template="green",
    )
    print("Done!")


if __name__ == "__main__":
    main()
