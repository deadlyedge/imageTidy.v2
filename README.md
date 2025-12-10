# imageTidy.v2

整理遗留图纸/照片/文档的辅助工具。目前的流程：
1. 使用 `collect_metadata.py` 扫描 `settings.py` 中的 `SOURCE_FOLDER`，收集每个文件的路径、扩展名和修改时间。
2. 通过 `generate_plan.py`（可接入 LLM）生成项目/时间段/类别配置并输出 `move_plan.csv`，用于人工审核。
3. 审核完后再用 `execute_plan.py` 按照计划移动文件，所有操作都会写入 `output/` 下的日志。

## 环境

所有 Python 依赖由 `pyproject.toml` 定义，请使用 `uv` 统一管理：

```bash
uv install      # 创建/更新虚拟环境并安装依赖
uv run python collect_metadata.py
```

不要直接用 `pip install`，避免在不同环境中产生版本不一致。

## 实际执行顺序

1. **收集元数据**  
   ```bash
   uv run python collect_metadata.py
   ```  
   产出 `output/metadata.json`（每个文件的原始记录）、`output/folder_summary.json`（内部统计）、`output/tag_summary.json`（关键词标签及其原始链路/映射）、`output/tag_input.json`（供 AI 的 tag list，只有关键字）、以及 `output/folder_overview.json`（概览说明：总文件数、目录数量与 ascii tree，每个节点带文件数，帮 AI 判断目录权重）。

2. **生成迁移计划**  
    ```bash
    export OPENAI_API_KEY=...
    uv run python generate_plan.py
   ```  
   该脚本会把 `output/tag_input.json` 与 `output/folder_overview.json` 作为 AI 输入，让模型以关键词和权重为主导，再生成项目别名/别称映射（时间段由本地 metadata 计算）。完成后会生成：
   - `output/plan_config.json`（项目/时间/类别配置，包含本地计算出的时间区间）  
   - `output/move_plan.csv`（详细迁移计划，供你审核）  
   - `move_plan.csv` 也会被拷贝一份到目标目录（`<source>-organized/move_plan.csv`），方便在整理好的结构下回顾。
   - 日志和摘要在 `output/generate_plan.log` / `output/plan_summary.json`。

3. **审核迁移计划**  
   打开 `output/move_plan.csv`，确认 `new_path` 字段里新的目录结构（`<time-range>-<project-name>/<category>`）没问题。计划表格确保每一次移动都有记录。

4. **执行迁移（可先 dry run）**  
   ```bash
   uv run python execute_plan.py --dry-run  # 只记录不移动
   uv run python execute_plan.py             # 执行移动
   ```  
   执行时日志会写入 `output/execute_plan.log`，会自动处理目标冲突（会在文件名后追加 `_dupN`）。  
   需要回滚整理结果？用 `uv run python execute_plan.py --revert` 会先校验目标目录下的 `move_plan.csv` 是否存在，若缺失则退出。恢复时，它会根据目标文件夹里的那份计划把文件移回原始路径。

## 目录说明
- `collect_metadata.py`：遍历 `SOURCE_FOLDER`，生成 `metadata.json`、`folder_summary.json`（内部统计）、`tag_summary.json`（关键词标签与原始链路/映射）、`tag_input.json`（AI 用的 tag list），并写出 `folder_overview.json`（概览，只保留 ascii tree 与总文件/目录统计，用于说明哪些分支承载最多文件）。
- `generate_plan.py`：用目录摘要询问 LLM 得到项目/类别建议，再用 metadata 自行计算时间区间，最终输出迁移计划。
- `execute_plan.py`：根据计划移动文件，支持 dry-run 和冲突解决。
- `output/`：所有中间文件与日志都在这里，默认被 `.gitignore` 忽略。

在每一步务必先 review `output/` 下的 CSV/JSON，再进入下一个阶段，确保不会误删或错移老文件。
