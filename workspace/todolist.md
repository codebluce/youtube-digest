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

---

## 已完成

处理完成后把整行从「待处理」剪切到这里，并补上产出路径；不需要保留登记时的猜测性备注。

| 完成日期 | video_id | 标题 | 主文 | 处理者备注 |
|---|---|---|---|---|
| — | — | — | — | （示例行） |
| 2026-07-30 | nilNLfW7izg | SK海力士：一家两次被扫地出门的公司，如何卡住全世界AI的脖子 | workspace/articles/2026-07-28-SK海力士：一家两次被扫地出门的公司，如何卡住全世界AI的脖子.md | 历史产出补录；已统一 article 中文命名。 |
| 2026-07-30 | rDkMK20YHIk | 大摩闭门会：AI 硬件跌 20% 不是终结，是三条裂痕同时暴露 | workspace/articles/2026-07-28-大摩闭门会：AI 硬件跌 20% 不是终结，是三条裂痕同时暴露.md | 历史产出补录；已统一 article 中文命名。 |
| 2026-07-30 | uilXQ1AAru8 | AI 上游硬件不是坏了，而是到了最容易被杠杆反噬的阶段 | workspace/articles/2026-07-28-AI 上游硬件不是坏了，而是到了最容易被杠杆反噬的阶段.md | 历史产出补录；已统一 article 中文命名。 |
| 2026-07-30 | fKoWrF49Qo8 | 特朗普的赚钱 2.0：当「阳光」从消毒剂变成防护罩 | workspace/articles/2026-07-29-特朗普的赚钱 2.0：当「阳光」从消毒剂变成防护罩.md | 历史产出补录；已统一 article 中文命名。 |
| 2026-08-02 | BV1V4Te6MEAu | 小Lin说《AI巨头们之间的资本混战，到底是个什么情况？》 | workspace/articles/2026-08-02-AI 巨头资本战争：你以为他们在砸钱买公司，其实是在互相抵押命根子.md | B 站首个多源端到端案例；无站内字幕，yt-dlp 下载 m4a + faster-whisper medium ASR；主文与卡片包 validator 73 PASS。 |
| 2026-08-02 | BV1x4EE6GE8h | Balle努力做字幕《英国记者采访Hasan结果变成辩论：不能把以色列和纳粹德国做类比吗？》 | workspace/articles/2026-08-02-一场采访如何变成话语权审判：Hasan、LBC 与“能不能类比纳粹”的争论.md | 无人工字幕轨；yt-dlp 下载 m4a + 本地 faster-whisper medium ASR；事件复盘型，主文与卡片包 validator 68 PASS。 |
| 2026-08-07 | if4FrsR3qb4 | 香港金融界演讲《K型分化的破局点：为什么中国把提振消费押在社会保障上》 | workspace/articles/2026-08-07-K型分化的破局点：为什么中国把提振消费押在社会保障上.md | 无官方字幕；yt-dlp 下载 webm + 本地 faster-whisper large-v3-turbo ASR（22.4 分钟，640 段）；宏观策略型，主文与卡片包 validator 72 PASS。 |
| 2026-08-16 | NEHcGq80GQ0 | 硅谷101《开源不是情怀是武器：中国模型厂商把「开放」本身做成了竞争打法》 | workspace/articles/2026-08-16-开源不是情怀是武器：中国模型厂商把「开放」本身做成了竞争打法.md | 官方字幕可用（596 段，23:02）；公司行业研究型，主文与卡片包 validator 73 PASS。 |

---

## 使用说明

- **状态**取值：`待处理` / `处理中（谁在处理）` / 完成后移入「已完成」表并从本表删除。
- **备注**列可以写：用户对这条视频的简短描述、期望的处理优先级、已知的转录困难（如"无字幕，需 ASR"）等——不强制填写。
- **认领处理中的条目**：把状态改成 `处理中（机器名或 agent 标识）`，避免多个 agent 重复处理同一条。处理完后从「待处理」表删除该行，转移到「已完成」表。
- 本文件跟随仓库默认双推（origin + gitee），任何一次登记或状态变更后都应提交推送，这样其他机器上的 agent 才能看到最新队列。
