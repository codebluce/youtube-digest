# Video Digest 待办清单

> 这是**入口登记表**，不是产出记录。用户每次发来一个视频链接（任意已注册源），agent 先在这里登记
> 一行，再询问是否用当前 agent 立即执行 digest。不同机器/不同 agent 共享同一个仓库，
> 谁有空、谁有 ASR 能力，谁就可以来认领「待处理」的条目——不需要是最初登记的那个 agent。
>
> 完整规则见 `SKILL.md` 的「入口登记（Intake Gate）」一节。

---

## 待处理

| 添加日期 | source | video_id | URL | 备注 | 状态 |
|---|---|---|---|---|---|
| 2026-08-01 | youtube | WTz7LaHuqMw | https://www.youtube.com/watch?v=WTz7LaHuqMw | 小Lin说《关税变脸与稀土反杀》，无官方字幕需 ASR fallback。Nolan 本机：yt-dlp.exe 已装（AppData\Roaming\Python\Python312\Scripts\yt-dlp.exe）、faster-whisper medium 已就绪（D:\models\huggingface\models--Systran--faster-whisper-medium）。卡点：本机网络直连 youtube.com 超时，yt-dlp 下载跑不动。下一位认领者若网络可用直接跑 SKILL.md 步骤 1 末尾 ASR fallback 命令即可 | 待处理 |
| 2026-08-02 | bilibili | BV1V4Te6MEAu | https://www.bilibili.com/video/BV1V4Te6MEAu/ | 小Lin说《AI巨头们之间的资本混战，到底是个什么情况？》(19.5 min)。B 站视频通常无人工字幕，多源骨架改造后首次端到端实测 | 处理中（Nolan-Claude） |

---

## 已完成

处理完成后把整行从「待处理」剪切到这里，并补上产出路径；不需要保留登记时的猜测性备注。

| 完成日期 | video_id | 标题 | 主文 | 处理者备注 |
|---|---|---|---|---|
| — | — | — | — | （示例行） |

---

## 使用说明

- **状态**取值：`待处理` / `处理中（谁在处理）` / 完成后移入「已完成」表并从本表删除。
- **备注**列可以写：用户对这条视频的简短描述、期望的处理优先级、已知的转录困难（如"无字幕，需 ASR"）等——不强制填写。
- **认领处理中的条目**：把状态改成 `处理中（机器名或 agent 标识）`，避免多个 agent 重复处理同一条。处理完后从「待处理」表删除该行，转移到「已完成」表。
- 本文件跟随仓库默认双推（origin + gitee），任何一次登记或状态变更后都应提交推送，这样其他机器上的 agent 才能看到最新队列。
