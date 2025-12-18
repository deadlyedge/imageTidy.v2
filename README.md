# imageTidy.v2

一个智能化的复杂文件结构整理工具，专门用于整理CAD图纸、照片和文档。通过AI智能分析项目名称、时间段和文件类型，自动生成整理计划并执行迁移。

## 核心功能

### 🤖 AI智能分析
- 使用Google Gemini 2.5 Flash模型进行智能项目识别
- 自动发现项目别名和变体名称
- 支持中英文文件夹名称识别
- 基于目录权重智能分类

### 📁 智能分类
- **项目分类**：自动识别和合并相似的项目名称
- **时间分类**：基于文件修改时间自动生成时间区间
- **文件类型分类**：支持CAD、照片、文档等文件类型

### 🔒 安全保障
- 支持dry-run预览模式
- 完整的操作日志记录
- 冲突自动解决机制
- 支持回滚恢复

### 📊 完整追踪
- 生成详细的迁移计划CSV
- 保留原始文件信息
- 提供执行摘要和统计

## 工作流程

### 第一步：收集元数据
使用 `collect_metadata.py` 扫描 `settings.py` 中的 `SOURCE_FOLDER`，收集每个文件的路径、扩展名和修改时间。

### 第二步：生成迁移计划
通过 `generate_plan.py`（可接入 LLM）生成项目/时间段/类别配置并输出 `move_plan.csv`，用于人工审核。

### 第三步：执行迁移
审核完后再用 `execute_plan.py` 按照计划移动文件，所有操作都会写入 `output/` 下的日志。

## 环境配置

所有 Python 依赖由 `pyproject.toml` 定义，请使用 `uv` 统一管理：

```bash
uv install      # 创建/更新虚拟环境并安装依赖
uv run collect_metadata.py
```

**重要**：不要直接用 `pip install`，避免在不同环境中产生版本不一致。

## 实际执行顺序

### 1. 收集元数据
```bash
uv run collect_metadata.py
```
产出以下文件：
- `output/metadata.json`（每个文件的原始记录）
- `output/folder_summary.json`（内部统计）
- `output/tag_summary.json`（关键词标签及其原始链路/映射）
- `output/tag_input.json`（供 AI 的 tag list，只有关键字）
- `output/folder_overview.json`（概览说明：总文件数、目录数量与 ascii tree，每个节点带文件数，帮 AI 判断目录权重）

### 2. 生成迁移计划
```bash
export OPENAI_API_KEY=...
uv run generate_plan.py
```

**覆盖缺失标签**：
如果想把当前 `tag_input.json` 中还没被 AI 覆盖的关键词下一轮再问一遍，可加 `--cover-missing`，脚本会以那些缺失 tag 作为第二轮输入。

该脚本会把 `output/tag_input.json` 与 `output/folder_overview.json` 作为 AI 输入，让模型以关键词和权重为主导，再生成项目别名/别称映射（时间段由本地 metadata 计算）。完成后会生成：

- `output/plan_config.json`（项目/时间/类别配置，包含本地计算出的时间区间）
- `output/move_plan.csv`（详细迁移计划，供你审核）
- `move_plan.csv` 也会被拷贝一份到目标目录（`<source>-organized/move_plan.csv`），方便在整理好的结构下回顾
- 日志和摘要在 `output/generate_plan.log` / `output/plan_summary.json`

### 3. 审核迁移计划
打开 `output/move_plan.csv`，确认 `new_path` 字段里新的目录结构（`<time-range>-<project-name>/<category>`）没问题。计划表格确保每一次移动都有记录。

### 4. 执行迁移（可先 dry run）
```bash
uv run execute_plan.py --dry-run  # 只记录不移动
uv run execute_plan.py             # 执行移动
```

执行时日志会写入 `output/execute_plan.log`，会自动处理目标冲突（会在文件名后追加 `_dupN`）。

**回滚功能**：
需要回滚整理结果？用 `uv run execute_plan.py --revert` 会先校验目标目录下的 `move_plan.csv` 是否存在，若缺失则退出。恢复时，它会根据目标文件夹里的那份计划把文件移回原始路径。

## 输出目录结构

整理后的目录结构遵循模式：`<time-range>-<project-name>/<category>`

例如：
```
2020-2021-龙湖固定家具/cad/
2020-2021-龙湖固定家具/photos/
2020-2021-龙湖固定家具/docs/
2022-龙湖地产项目/cad/
```

## 模块说明

- `collect_metadata.py`：遍历 `SOURCE_FOLDER`，生成各类元数据文件
- `generate_plan.py`：用目录摘要询问 LLM 得到项目/类别建议，再用 metadata 自行计算时间区间，最终输出迁移计划
- `execute_plan.py`：根据计划移动文件，支持 dry-run 和冲突解决
- `imagetidy/planning.py`：核心规划逻辑，包含项目匹配、时间范围推导等算法
- `output/`：所有中间文件与日志都在这里，默认被 `.gitignore` 忽略

## 配置文件

在 `settings.py` 中可以配置：
- `SOURCE_FOLDER`：要整理的源文件夹路径
- `MODEL_NAME`：使用的AI模型（默认为 google/gemini-2.5-flash）
- `AI_PROMPT`：AI分析的提示词

## 注意事项

⚠️ **安全提醒**：整理历史文件是一个复杂且风险较高的任务，务必多加小心。建议先在小范围内测试脚本和流程，确认无误后再大规模执行。

在每一步务必先 review `output/` 下的 CSV/JSON，再进入下一个阶段，确保不会误删或错移老文件。

## 版本信息

- 当前版本：v1.0.1
- Python要求：>=3.12
- 主要依赖：openai>=2, python-dotenv>=1.2.1

祝你整理顺利！
