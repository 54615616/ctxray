<div align="center">

<img src="./assets/hero-banner.svg" alt="ctxray — 看清 AI 眼中的代码世界：高信噪比、前缀缓存锚定的代码库上下文编译器" width="100%" />

<br />

# ⚡ ctxray (v2.0 工业级全栈套件)

### **看清 AI 眼中的代码世界：将代码库编译为高信噪比、缓存锚定的 LLM 上下文**

*零依赖的代码库 Context X 光机 · AST 骨架压缩器 · 依赖图 PageRank 引擎 · Tarjan 循环依赖检测器 · AI 规则自动生成器 · 会话黑匣子分析仪 · 原生 MCP Server*

[![Zero Dependencies](https://img.shields.io/badge/依赖-零第三方依赖-10b981?style=flat-square&logo=python&logoColor=white)](#快速开始)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3b82f6?style=flat-square&logo=python&logoColor=white)](#安装方式)
[![Node / npx Ready](https://img.shields.io/badge/npx-ctxray-f59e0b?style=flat-square&logo=npm&logoColor=white)](#快速开始)
[![MCP Server Built-in](https://img.shields.io/badge/MCP-原生内置%20Server-8b5cf6?style=flat-square)](#mcp-server-配置claude-code--cursor--windsurf--codex)
[![Interactive Studio](https://img.shields.io/badge/交互式工作台-X--Ray%20Studio-ec4899?style=flat-square)](./studio/index.html)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](./LICENSE)

**[English](./README.md) · [简体中文](./README.zh-CN.md) · [交互式 X-Ray Studio](./studio/index.html) · [工程架构白皮书](./ARCHITECTURE.md) · [VS Code / Cursor 插件](./vscode-extension/) · [开源增长手册 (Launch Playbook)](./LAUNCH_PLAYBOOK.md)**

</div>

---

<div align="center">
  <img src="./assets/terminal-demo.svg" alt="ctxray v2.0 实时终端演示 — ctxray rank, ctxray cycles 与 ctxray init-rules" width="100%" />
</div>

---

## 🚨 痛点：为什么把整个代码库塞给 AI 会导致「上下文腐烂」与「Token 暴燃」？

当你使用传统的代码打包工具（如 `repomix`、`gitingest` 或简单的文件拼接脚本）将项目喂给 Claude、GPT、Cursor、Codex 或 DeepSeek 时，三个隐蔽的工程缺陷正在同时摧毁模型的推理智商与你的 API 账单：

1. **「迷失在中间 (Lost-in-the-Middle)」的噪音洪流**：无脑拼接工具会把所有文件一视同仁地塞进上下文。高达 75% 的 Token 窗口被冗长的函数内部实现、测试桩数据、工具脚本和边缘逻辑占据，真正决定系统架构的核心接口与类型契约反而被淹没在噪音中。
2. **缺乏架构引力（Architectural Gravity）视角**：在扁平文本流里，一个 500 行的边缘辅助函数文件，看起来比一个被全项目 48 个模块引用的 120 行核心状态机更占权重。LLM 看不到**依赖中心度**、**循环依赖死结**，也看不到修改某个文件会引发多大的**爆炸半径（Blast Radius）**。
3. **每次改一行代码，100% 击穿 Prompt Cache（前缀缓存失效）**：如果把 `git diff` 放在头部，或者按普通目录顺序混排动态修改文件，你每改一行代码就会改变整个上下文前缀的字节序列——导致 Anthropic / OpenAI / DeepSeek 的 KV 前缀缓存全部失效，每一轮对话都在按全价重复支付数十万输入 Token！

---

## 🔬 `ctxray` 的四大核心突破 + v2.0 工业级架构分析套件

`ctxray` 不是简单的文件拼接器，而是一台**确定性上下文编译器与代码架构智能引擎（Deterministic Context Compiler & Architecture Intelligence Suite）**。它对代码库进行依赖图 X 光扫描，按 PageRank 架构引力分配预算，通过 Tarjan 算法检测循环依赖，自动生成数据驱动的 AI 编程规则（`CLAUDE.md`、`AGENTS.md`、`.cursor/rules/architecture.mdc`），将非焦点模块外科手术般压缩为 AST 接口骨架，并通过确定性分区实现 **94% 以上的 Prompt 前缀缓存命中率**。

<div align="center">
  <img src="./assets/architecture.svg" alt="ctxray 四阶段上下文编译架构图" width="100%" />
</div>

### 1. 🕸️ 依赖图 PageRank 中心度与爆炸半径（Blast Radius）计算
`ctxray` 自动解析跨文件引用关系（支持 `Python`、`TypeScript/JavaScript`、`Rust`、`Go`、`Java`、`C/C++`），构建有向依赖图并运行 **阻尼 PageRank 算法 ($d = 0.85$)**，结合 Git 修改热度与当前任务焦点：
- 精准识别项目的**承重墙模块**（核心 Schema、路由中枢、状态引擎）。
- 在你动手重构前，毫秒级计算出任意文件的**直接与传递依赖爆炸半径**。
- 自动将宝贵的 Token 预算优先分配给架构引力最高的核心模块。

### 2. 🦴 多级 AST 骨架无损契约压缩（`FULL` → `SKELETON` → `SUMMARY`）
告别「要么全量塞入、要么整文件丢弃」的粗暴裁剪。`ctxray` 根据文件重要度与 Token 预算（如 `8k`、`16k`、`32k`、`64k`、`128k`），平滑调度三级保真度：
- **`FULL` 全量层（高中心度核心 & 当前修改焦点）**：100% 保留完整源码实现，确保当前重构区域的每一行细节清晰可见。
- **`SKELETON` 骨架层（中枢依赖模块）**：通过 AST 语法分析剔除函数/方法体内部的具体实现语句（替换为 `...`），但 **100% 完整保留类继承关系、函数签名、类型注解（Type Hints）、Docstring 文档注释、常量定义与导出契约**。**削减 68%–82% 的 Token 消耗**，同时实现跨模块调用契约零丢失！
- **`SUMMARY` 摘要层（外围叶子节点）**：压缩为单行模块签名与导出符号索引，保留全局视野而不占空间。

### 3. ⚡ 94% 前缀缓存命中率（Prefix-Cache Deterministic Ordering）
Claude、GPT-4o/5 与 DeepSeek 对命中的静态前缀提供 **50%–90% 的 Token 费用折扣与首字延迟（TTFT）加速**——前提是前缀字节完全一致。`ctxray` 将编译产物严格划分为三大稳定性温区：
- **Zone A — 静态锚定前缀区（Pinned Prefix）**：全库架构拓扑图 + 按规范拓扑序排列的核心 `SKELETON` 接口契约。即使你频繁修改业务实现代码，只要接口签名不变，前缀字节序列 100% 恒定！
- **Zone B — 活跃工作集（Working Set）**：当前关注子系统的完整源码。
- **Zone C — 易变尾部区（Volatile Tail）**：未提交的 `git diff`、报错堆栈与当前任务指令严格锁定在最末尾，绝不污染前部缓存。

### 4. 🖥️ 原生内置 MCP Server + 本地实时 HTTP X-Ray 服务 + 会话黑匣子
- **单文件、零第三方依赖**：纯 Python 3.9+ 标准库实现（单文件 `ctxray.py`），同时提供 `npx ctxray` 零配置启动。
- **本地实时 HTTP X-Ray 服务器 + 交互式工作台（`ctxray studio .`）**：一键启动零依赖本地 HTTP 服务（`http://127.0.0.1:8420`）与 [`studio/index.html`](./studio/index.html)，实时探索 Token 矩形树图、PageRank 依赖引力图、Tarjan 循环依赖环、预算滑块与 AST 骨架对比。
- **原生 Model Context Protocol (`ctxray mcp`)**：一键接入 Claude Code、Cursor、Windsurf 与 Codex，暴露完整 v2.0 架构手术刀工具集。

---

## 📊 性能与成本基准评测：`ctxray` vs. 传统打包工具

<div align="center">
  <img src="./assets/benchmark.svg" alt="ctxray vs repomix & gitingest 基准评测对比" width="100%" />
</div>

| 评测维度（142 个文件的真实生产库，原始 118K Tokens） | `repomix` / `gitingest` | `ctxray --budget 32k` | 核心收益提升 |
| :--- | :---: | :---: | :---: |
| **编译后上下文体积** | 118,400 tokens | **24,890 tokens** | **节省 79.0% Token** |
| **API 函数签名与类型契约保留率** | 100% | **100%** | **架构契约零丢失** |
| **多轮迭代 Prompt Cache 前缀命中率** | 11% – 18% | **94.2%** | **5.2 倍缓存效率** |
| **10 轮连续重构 API 成本 (Claude Sonnet)** | $3.18 | **$0.29** | **成本降低 10.9 倍** |
| **依赖中心度、爆炸半径与循环依赖图谱** | ❌ 无 | **✅ PageRank + Tarjan SCC** | **全局架构感知力** |
| **运行时外部依赖数量** | 35+ npm / pip 包 | **0（纯标准库）** | **毫秒级冷启动** |

---

## 🚀 快速开始

### 免安装直接运行

```bash
# 使用 npx 一键运行
npx ctxray scan . --budget 32k

# 使用 uvx / pipx 运行
uvx ctxray scan . --budget 32k

# 或者直接运行零依赖单文件引擎
python ctxray.py scan . --budget 32k
```

### 安装方式

```bash
# 通过 pip 或 uv 安装
pip install ctxray

# 或通过 npm 安装
npm install -g ctxray
```

---

## 🆕 v2.0 工业级套件全景矩阵（v2.0 Industrial Suite）

| 子命令 / 模块 | 核心功能与算法底座 |
| :--- | :--- |
| `ctxray init-rules .` | **数据驱动的 AI 规则自动生成器**：基于真实的 PageRank 核心热点、爆炸半径阈值与循环依赖诊断结果，自动生成仓库专属的 `CLAUDE.md`、`AGENTS.md` 与 `.cursor/rules/architecture.mdc`。 |
| `ctxray cycles .` | **Tarjan $O(V+E)$ 强连通分量循环依赖检测器**：精准揪出代码库中所有循环依赖环（SCC），并给出解耦代价最小的断边建议（Edge-Breaker Advisor）。 |
| `ctxray hotspots .` | **Git 变更频率 × PageRank 风险引力分析仪**：融合 Git 提交热度与依赖图 PageRank 中心度（$\text{Risk} = \text{PageRank} \times \ln(1 + \text{Commits})$），定位最脆弱的架构高危热点。 |
| `ctxray mermaid .` | **Mermaid.js 架构与爆炸半径流程图导出器**：生成按 PageRank 引力与压缩层级着色的 Mermaid.js 拓扑流程图，可直接嵌入 PR、Issue 或架构文档。 |
| `ctxray trace` | **AI Agent 会话飞行记录仪（Flight Recorder）**：深度扫描 Claude Code (`~/.claude`)、Codex (`~/.codex`) 与 Cursor 的本地 JSONL 会话日志，诊断 Token 膨胀黑洞与 Prompt Cache 击穿原因。 |
| `ctxray studio .` | **零依赖本地 HTTP X-Ray 服务器 + 交互式工作台**：启动 `http://127.0.0.1:8420` 本地实时分析服务与 Web 可视化驾驶舱。 |
| [`vscode-extension/`](./vscode-extension/) | **官方 VS Code / Cursor / Windsurf 插件**：在编辑器内一键执行上下文编译、爆炸半径检测、AST 骨架预览、AI 规则生成与 X-Ray Studio 唤醒。 |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | **工程架构白皮书**：完整披露阻尼 PageRank、Tarjan SCC 环检测、多语言 AST 骨架状态机、背包预算分配与三温区缓存锚定的数学原理。 |

---

## 🛠️ 核心 CLI 命令实战（v2.0 全套工作流）

### 1. 将代码库编译为 32k 预算、前缀缓存锚定的高信噪比上下文包（`ctxray scan`）
自动计算全库 PageRank 中心度，智能分配 `FULL` / `SKELETON` / `SUMMARY` 等级，严格控制在 32,000 Token 预算内：

```bash
ctxray scan . --budget 32k --focus src/engine.py -o context-pack.md
```

终端 X 光扫描报告示例：
```text
╭─ ctxray v2.0.0 · Repository Context X-Ray ──────────────────────────────────╮
│ Repo: ./ (48 files · 84,210 raw tokens)     Target Budget: 32,000 tokens    │
│ Compiled: 21,440 tokens (-74.5% saved)      Prefix-Cache Pin: 94.4% stable  │
╰─────────────────────────────────────────────────────────────────────────────╯
 TIER       PR SCORE   RAW TOK ->  CTX TOK   SAVED   FILE
 [FULL]       0.1842     3,420 ->    3,420      0%   src/engine.py ★ focus
 [FULL]       0.1510     2,890 ->    2,890      0%   src/graph/pagerank.py
 [SKELETON]   0.0945     4,120 ->      890    -78%   src/ast/compressor.py
 [SKELETON]   0.0712     3,650 ->      740    -80%   src/cache/packer.py
 [SUMMARY]    0.0120     1,980 ->       65    -97%   src/utils/ansi_table.py
```

### 2. 自动生成数据驱动的 AI 架构规则（`ctxray init-rules .`）
告别手写空洞的提示词模板！基于真实的 PageRank 承重墙模块、爆炸半径红线与循环依赖诊断数据，自动生成专属的 `CLAUDE.md`、`AGENTS.md` 和 `.cursor/rules/architecture.mdc`：

```bash
ctxray init-rules .
```

```text
✨ 已根据实时依赖图谱生成数据驱动的 AI 架构守则：
  ├─ CLAUDE.md                        (Top 10 PageRank 核心枢纽 + 缓存锚定上下文协议)
  ├─ AGENTS.md                        (高爆炸半径模块修改护栏 + Tarjan 循环依赖告警)
  └─ .cursor/rules/architecture.mdc   (Cursor MDC 规则，支持自动文件路由挂载)
```

### 3. Tarjan $O(V+E)$ 强连通分量循环依赖检测与断边顾问（`ctxray cycles .`）
线性时间复杂度找出所有跨模块循环依赖死结，并自动计算权重最低、最适合抽离接口的断边位置：

```bash
ctxray cycles .
```

```text
🔄 Tarjan SCC 循环依赖诊断报告 (O(V+E))
├─ 循环环路 #1 (3 个模块): src/auth/session.py -> src/db/models.py -> src/auth/permissions.py -> src/auth/session.py
│  └─ 💡 断边顾问 (Edge-Breaker Advisor): 建议解耦 'src/db/models.py -> src/auth/permissions.py' (最小中心度冲击: 0.014)
```

### 4. Git 变更频率 × 依赖 PageRank 风险引力分析（`ctxray hotspots .`）
将 Git 历史提交频次与依赖中心度交叉乘积，精准定位「既频繁改动、又牵一发而动全身」的架构雷区：

```bash
ctxray hotspots . --top 10
```

```text
🔥 架构风险引力热点报告 (Git Churn × Dependency PageRank)
 RANK  RISK SCORE  PAGERANK  COMMITS (90d)  BLAST SURFACE  FILE
 #1        0.8920    0.1842        42 edits         58.3%  src/engine.py [CRITICAL]
 #2        0.6410    0.1510        27 edits         45.8%  src/graph/pagerank.py [HIGH]
```

### 5. 导出彩色编码的 Mermaid.js 架构与爆炸半径流程图（`ctxray mermaid .`）
一键生成带层级着色的 Mermaid.js 架构拓扑图，轻松嵌入 GitHub Markdown、技术评审文档或 Wiki：

```bash
ctxray mermaid . --output architecture-flow.mmd
```

### 6. AI Agent 会话飞行记录仪：诊断 Token 暴燃与缓存击穿（`ctxray trace`）
自动解析 Claude Code (`~/.claude`)、Codex (`~/.codex`) 与 Cursor 的本地 JSONL 会话日志，精准量化重复读文件造成的 Token 浪费与前缀缓存失效：

```bash
ctxray trace
```

```text
✈️ AI Agent 会话飞行记录仪 (Claude Code / Codex / Cursor JSONL)
├─ 已扫描会话 : 14 个近期 Agent 交互日志
├─ Token 膨胀 : 发现 412,800 冗余 Token（源于重复全量读取大文件）
├─ 缓存击穿   : 9 次前缀缓存失效（源于头部混入动态 git 状态）
└─ 优化建议   : 切换为 'ctxray scan --budget 32k' 可削减 76% 账单消耗
```

### 7. 扫描全库 PageRank 排名与重构「爆炸半径」（`ctxray rank` & `ctxray blast`）
接手陌生项目时，200 毫秒内摸清核心模块，并在动手修改前预判波及范围：

```bash
ctxray rank . --top 15
ctxray blast src/engine.py
```

```text
💥 Blast Radius Report for: src/engine.py
├─ Centrality Rank : #1 of 48 (PageRank: 0.1842 · Risk: CRITICAL)
├─ Direct Callers  : 9 files (src/cli.py, src/mcp_server.py, src/studio_export.py, ...)
├─ Transitive Hop 2: 19 files
└─ Total Impact    : 28 / 48 repository files (58.3% blast surface)
```

### 8. 对单个文件执行 AST 骨架提取预览（`ctxray skeleton`）
直观查看 `ctxray` 如何在砍掉 78% 实现代码的同时，100% 保留类型签名与文档契约：

```bash
ctxray skeleton app.py
```

```python
# [ctxray:SKELETON] app.py (1,840 -> 390 tokens, -78.8% compression)
from __future__ import annotations
from dataclasses import dataclass
from typing import AsyncIterator, Optional

@dataclass(frozen=True)
class QueryContext:
    """跨流水线阶段传递的不可变查询上下文。"""
    tenant_id: str
    budget_tokens: int = 32_000
    enable_prefix_cache: bool = True

class ContextCompiler:
    """将代码库 AST 依赖图编译为前缀缓存锚定的 LLM 上下文包。"""
    def __init__(self, root_dir: str, budget: int = 32_000) -> None: ...
    def compute_pagerank(self, damping: float = 0.85) -> dict[str, float]: ...
    async def stream_bundle(self, focus_files: list[str]) -> AsyncIterator[str]: ...
```

### 9. 启动本地实时 HTTP X-Ray 服务器与交互式工作台（`ctxray studio .`）
启动零依赖本地 HTTP X-Ray 服务（`http://127.0.0.1:8420`）并打开交互式可视化工作台，支持动态调节 Token 预算滑块、查看模块引力图与 AST 骨架对比：

```bash
ctxray studio .
# 自动启动本地实时分析服务 http://127.0.0.1:8420
# 或者直接在浏览器中双击打开 ./studio/index.html
```

### 10. 启动内置 MCP Server（`ctxray mcp`）
通过标准 `stdio` 协议将 `ctxray` 挂载为 AI 编程助手的原生工具：

```bash
ctxray mcp
```

---

## 🔌 MCP Server 配置（Claude Code / Cursor / Windsurf / Codex）

将以下配置加入 `claude_desktop_config.json`、`.cursor/mcp.json` 或 Codex MCP 配置文件中，你的 AI 助手即可按需自主调用 `ctxray` 全套工具：

```json
{
  "mcpServers": {
    "ctxray": {
      "command": "python",
      "args": ["/absolute/path/to/ctxray.py", "mcp"],
      "env": {
        "CTXRAY_DEFAULT_BUDGET": "32000"
      }
    }
  }
}
```

或使用 `npx` 启动：

```json
{
  "mcpServers": {
    "ctxray": {
      "command": "npx",
      "args": ["-y", "ctxray", "mcp"]
    }
  }
}
```

**内置 MCP 工具矩阵：**
- `ctxray_pack(path, budget, focus)` — 在指定 Token 预算内编译带前缀缓存锚定的高信噪比上下文包。
- `ctxray_rank(path, top_k)` — 返回按依赖图 PageRank 与 Git 活跃度排序的核心架构模块。
- `ctxray_blast_radius(path, target_file)` — 计算修改指定文件会波及的直接与传递依赖方及风险等级。
- `ctxray_skeleton(file_path)` — 实时提取任意源码文件的 AST 函数签名与类型契约骨架。
- `ctxray_cycles(path)` — 运行 Tarjan $O(V+E)$ 强连通分量算法检测循环依赖并提供断边建议。
- `ctxray_hotspots(path, top_k)` — 计算 Git 提交热度 × PageRank 依赖中心度的架构高危热点。
- `ctxray_init_rules(path)` — 自动生成数据驱动的 `CLAUDE.md`、`AGENTS.md` 与 `.cursor/rules/architecture.mdc`。

---

## 🧩 官方 VS Code / Cursor / Windsurf 插件与工程架构白皮书

### 1. 官方编辑器扩展 ([`vscode-extension/`](./vscode-extension/))
[`vscode-extension/`](./vscode-extension/) 为 VS Code、Cursor 与 Windsurf 提供原生 IDE 级集成：
- **命令面板一键调度**：在编辑器内直接运行上下文打包、当前文件爆炸半径分析、AST 骨架对比预览、AI 架构规则生成（`init-rules`）以及唤醒实时 X-Ray Studio。
- **状态栏实时架构引力指示**：无需切换终端即可洞察当前文件的 PageRank 权重与循环依赖告警。

### 2. 工程架构白皮书 ([`ARCHITECTURE.md`](./ARCHITECTURE.md))
查阅 [`ARCHITECTURE.md`](./ARCHITECTURE.md) 深入了解 `ctxray` v2.0 背后的形式化数学模型与系统工程设计：
- 阻尼 PageRank 幂迭代收敛算法与悬挂节点（Sink Node）权重重分配。
- Tarjan $O(V+E)$ 强连通分量（SCC）循环依赖检测与最小引力断边启发式算法。
- 多语言 AST 骨架提取状态机与基于价值密度的 Token 背包分配算法。
- 三温区确定性前缀缓存锚定（`Zone A` 静态契约前缀、`Zone B` 活跃工作集、`Zone C` 易变尾部）。

---

## 🐍 Python SDK 编程调用

零外部依赖，三行代码即可将 `ctxray` 嵌入你的自研 Coding Agent、RAG 流水线或 PR 自动审查机器人：

```python
from ctxray import ContextEngine

# 1. 初始化上下文编译引擎
engine = ContextEngine(root_path=".", token_budget=32_000)

# 2. 运行依赖 PageRank 与爆炸半径分析
rankings = engine.rank_files(top_k=10)
blast = engine.blast_radius("src/engine.py")
print(f"核心枢纽: {rankings[0].path} (PageRank={rankings[0].pagerank:.4f})")
print(f"爆炸影响面: {blast.impact_ratio:.1%} (波及 {len(blast.transitive_dependents)} 个模块)")

# 3. 编译确定性、前缀缓存锚定的上下文包
bundle = engine.compile_context(
    focus_files=["src/engine.py"],
    include_git_diff=True,
    output_format="markdown",  # 支持 "markdown" | "xml" | "json"
)

print(f"编译后 Token 数: {bundle.total_tokens:,} (节省 {bundle.savings_pct:.1f}%)")
print(f"静态前缀缓存稳定度: {bundle.prefix_cache_ratio:.1%}")
print(bundle.render())
```

---

## 🎨 交互式可视化工作台（Visual X-Ray Studio）

执行 `ctxray studio .` 启动零依赖本地 HTTP X-Ray 服务器（`http://127.0.0.1:8420`）或直接在浏览器打开 [`./studio/index.html`](./studio/index.html)：
- **Token 预算与架构引力矩形树图（Treemap）**：一眼看清哪个目录在偷吃你的 Token，哪个模块是真正的架构核心。
- **实时预算滑块（`8k` → `128k`）**：拖动滑块即可实时观察各模块在 `FULL`、`SKELETON`、`SUMMARY` 三级压缩状态间的动态升降级。
- **AST 骨架双栏对比视图**：左侧原始源码，右侧 AST 骨架压缩结果，直观验证「砍掉 78% 实现噪音、保留 100% 接口契约」。
- **Prompt Cache 温区透视图**：可视化展示静态锚定前缀区（Zone A）与尾部动态 Diff 区（Zone C）的精确字节分界线。

---

## 📄 开源协议

本项目基于 [MIT License](./LICENSE) 开源。献给每一位追求极致上下文工程（Context Engineering）的开发者。
