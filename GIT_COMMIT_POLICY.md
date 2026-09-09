# TalkWise Git 提交规范门禁

本仓库使用 Husky 和 commitlint 校验提交信息，同时保留已有 Python `pre-commit` 配置。

## 必须满足

1. 标题符合 `type(scope): 中文摘要`。
2. `type` 为小写英文，并属于允许列表：`feat`、`fix`、`docs`、`style`、`refactor`、`perf`、`test`、`build`、`ci`、`chore`、`revert`、`i18n`。
3. subject 必须包含中文摘要。
4. body 非空，且至少包含一项有序编号列表（`N. 说明`）。
5. 编号项下可使用 `-` 或 `*` 表达子项。

## 推荐格式

```text
feat(training): 增加训练场景能力

功能分组
  1. 新增训练入口
     - 保留现有会话状态
     - 增加失败提示

测试
  1. 更新训练和后端测试
```

编号前的两个空格是排版建议，不是单独的强制规则。

## 本地验证

```powershell
npm exec --no -- commitlint --edit .tmp\commit-message.txt
git diff --check
```
