# 飞书应用配置指南（发送文件必备）

自定义机器人 webhook **不能发文件**，必须创建飞书自建应用。全程约 10 分钟。

## 步骤

1. **创建应用**：登录 [飞书开放平台](https://open.feishu.cn/) → 开发者后台 → 创建企业自建应用 → 记录 **App ID**（`cli_` 开头）和 **App Secret**。

2. **添加机器人能力**：应用详情 → 添加应用能力 → 机器人。

3. **开通权限**（权限管理 → API 权限）：
   - `im:message`（获取与发送单聊、群组消息）
   - `im:message:send_as_bot`（以应用身份发消息）
   - `im:file`（上传文件，发文件消息必需）

4. **发布版本**：版本管理与发布 → 创建版本 → 提交发布（企业内应用通常自动通过或需管理员审批一次）。

5. **拿 RECEIVE_ID**：
   - **发群里**：把机器人拉进目标群 → 用管理员或任一成员身份调用 `GET /open-apis/im/v1/chats`（需 `im:chat:readonly` 权限）→ 找到该群的 `chat_id`（`oc_` 开头）。RECEIVE_ID_TYPE=`chat_id`。
   - **发个人**：先让该用户在飞书里给机器人发一句话，或用邮箱作为 receive_id：RECEIVE_ID_TYPE=`email`，RECEIVE_ID=用户企业邮箱（最简单，无需查 open_id）。

6. **配置环境变量**（写入云端 `~/.bashrc` 或 Hermes 的 env 配置）：

```bash
export FEISHU_APP_ID="cli_xxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxx"
export FEISHU_RECEIVE_ID="oc_xxxxxxxx"        # 或邮箱
export FEISHU_RECEIVE_ID_TYPE="chat_id"       # 用邮箱则改为 email
```

## 常见报错

| code | 含义 | 处理 |
|---|---|---|
| 99991663 | receive_id 无效 / 类型不匹配 | 核对 ID 前缀：`oc_`=chat_id、`ou_`=open_id；用邮箱就设 email |
| 99991672 | 机器人不在群里 / 无权限发消息 | 把机器人拉进群；检查 `im:message` 权限 |
| 99991668 | 应用未发布或被停用 | 回开发者后台确认版本已发布生效 |
| 230002 | 文件上传权限不足 | 补 `im:file` 权限后重新发布版本 |

## 测试

```bash
echo "hello feishu" > /tmp/test.md
uv run python3 SKILL_DIR/scripts/send_feishu.py /tmp/test.md --text "delivery test"
```

成功会打印 `{"ok": true, "message_id": ...}`，群里同时收到文字和 test.md 文件。
