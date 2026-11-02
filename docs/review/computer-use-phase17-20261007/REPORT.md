# 第十七阶段：限定范围发布与生产复核

日期：2026-10-07。结论：第十五阶段的下载异常提示、原版本记录及重新交付草稿入口已发布至生产前端，Computer Use 复核通过。后端没有重启，生产任务未被修改。

## 发布范围如何确认

在临时源码副本中仅撤回第十五阶段的前端修改，重新执行 Vite 构建。生成的 CommandCenter-sXc6IJ9f.js、CommandCenter-CbkDIc5u.css、commandCenter-bFMcDGEL.js 与发布前生产文件逐字节一致。这为仅发布该功能提供了构建基线，不依赖整个工作区的 Git diff 推断。

新指挥中心引用的共享依赖与生产文件逐字节一致；新 API 模块与旧模块的唯一差异是下载请求的 suppressErrorToast。保留生产其他页面及旧资源，只新增以下资源并原子更新 index.html：

- CommandCenter-CS5wr00t.js
- CommandCenter-2eTYgWrM.css
- commandCenter-ROI9GUXX.js
- main-phase17-895d3da4dd47.js

最后一项基于生产入口，仅替换指挥中心 JS/CSS 的引用；没有采用包含其他工作区改动的整站新入口。发布后核对原有 574 个非入口文件全部未变。旧资源仍保留，已打开的旧页面可以继续加载其原依赖，刷新后使用新入口。

## 验证结果

- 14 项相关前端测试通过，包括真实 Vue/Element Plus 组件上的异常提示、草稿引用、禁止自动提交、已有草稿保护、页面刷新保留、成功重试清除错误；既有审批与补偿显示回归同时通过。
- vue-tsc -b 通过，基线 Vite 构建通过，发布脚本 Python 编译检查及 git diff --check 通过。
- 在 localhost:3047 使用实际候选发布包进行 Computer Use：修改隔离文件后下载显示具体版本错误，重新交付按钮正确填写草稿并提示尚未启动任务。没有在该夹具提交任务。
- 发布前生产 active_missions、running_steps、running_compensations 均为 0。
- 生产 localhost:3021 浏览器显示新版本提示和可展开的登记 SHA256；实际下载既有 revised.md 成功，下载内容哈希与登记值一致。
- 生产健康为就绪，2/2 执行实例在线、失联 0、过期租约 0。初次进入时旧开发会话失效，按页面提示刷新后恢复正常，没有更改认证配置。
- 历史 H 任务的两条证据警告仍保留，没有将试点模式的完成记录改写为严格验收通过。页面“正在推进 6”是既有汇总口径，不应解释为 6 个正在运行的步骤；执行租约活跃为 0。

## 回退与发布产物

release/ 保存本次四个资源和入口，index-before.html 保存原入口，release-manifest.json 保存全部哈希。发布与回退都检查当前入口，避免覆盖之后的其他发布。

在生产 dist 的独立副本上实际执行了回退和重新发布，两次哈希断言通过；生产入口保持不变。需要回退本次功能时，从仓库根目录运行：

```sh
backend/venv/bin/python backend/scripts/prepare_phase17_frontend_release.py --rollback
```

回退只恢复原入口，不删除新增资源。此命令只适用于生产入口仍为本次版本；若已发生其他发布会拒绝执行，需要重新核对范围。

## 边界与后续

本阶段完成前端发布，不代表长期无人值守能力已经全部验收。重新交付任务之间仍通过目标文本追溯，尚无结构化双向版本关系；草稿也未新增跨整页重载保存。更长时间运行、远端工具故障和并发重新交付仍属后续验证范围。

下一阶段可以优先解决草稿在整页刷新后丢失的问题，明确保存范围、恢复提示和清理行为，并用 Computer Use 验证；无需继续重复已通过的同一下载正向场景。

## 证据

frontend-tests.txt、typecheck.txt、baseline-build.txt、baseline-match.json、baseline-sources/：测试及构建基线。

candidate-ui.txt、downloads.jsonl：候选包交互验证。

production-before.txt、production-ui.txt、production.png、production-download.json：生产前后检查与下载证据。

publish.txt、publication-audit.json、rollback-drill.json、release-manifest.json、release/：发布、完整性及回退演练记录。
