# 归档目录 — 不得作为写作参考

> ⚠️ **本目录下的文件不符合当前 `references/article-blueprint.md` v2.0 规范。**
> 它们是蓝图迭代过程中的历史版本，保留仅供对照演进过程。
>
> **任何 agent 在写新文章时，不得参考本目录下的任何文件。**
> 参考它们会导致模块缺失、可信度标记遗漏等漂移。正确的参考实现见上级目录中通过
> `scripts/validate_output.py` 校验的产出。

## 文件说明

| 文件 | 说明 | 为什么不合规 |
|---|---|---|
| `_sample-blueprint-v2.md` | 蓝图改造方案的格式演示样本 | **所有数字均为占位虚构**，非真实视频内容；且模块集合对应已废弃的中间设计 |
| `nilNLfW7izg-sk-hynix-hbm-v2.md` | SK海力士 P0-only 版本 | 真实内容，但缺 P1 模块（知识网络 / 多空对照 / 立场脚手架 / 跟踪清单 / UP主立场），跑校验会 FAIL |
| `2026-07-28-rDkMK20YHIk-morgan-stanley-macro-outlook-v1-noncompliant.md` | 大摩闭门会 v1（蓝图 v2 锁定前的旧格式） | 缺 M01 内容类型行，validator 无法识别类型；且无 `-cards.md` 卡片包配对，双产物缺一。**已按 v2.0 蓝图重制，见下方合规产出** |

## 同一视频的合规产出

`nilNLfW7izg`（SK海力士）：

```
../2026-07-28-nilNLfW7izg-sk-hynix-hbm.md         主文
../2026-07-28-nilNLfW7izg-sk-hynix-hbm-cards.md   卡片包
```

`rDkMK20YHIk`（大摩闭门会，基于既有内容重构——原始转录稿在本机不完整，仅存开场 418 字，未新增字幕之外的数字或事实，详见主文末尾说明）：

```
../2026-07-28-rDkMK20YHIk-morgan-stanley-macro-outlook.md         主文
../2026-07-28-rDkMK20YHIk-morgan-stanley-macro-outlook-cards.md   卡片包
```

验证方式：

```bash
python3 scripts/validate_output.py workspace/articles/2026-07-28-nilNLfW7izg-sk-hynix-hbm.md
python3 scripts/validate_output.py workspace/articles/2026-07-28-rDkMK20YHIk-morgan-stanley-macro-outlook.md
python3 scripts/audit_workspace.py   # 全仓审计：双产物配对/transcript归档/逐篇校验
```
