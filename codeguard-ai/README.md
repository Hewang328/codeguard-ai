# CodeGuard AI - 多 Agent 协作代码审查系统

## 项目简介
基于 LangGraph 的多 Agent 代码审查工具，自动分析 Python 代码的**架构、规范、安全性**，并生成结构化报告，可集成 CI/CD 或 GitHub PR。

## 核心逻辑流（长链推理 + 多Agent协作）
1. **结构分析 Agent** → 解析 AST，统计行数和导入，由 LLM 评估架构合理性。
2. **风格检查 Agent** → 按 PEP8/Google 风格指南审查命名、格式、注释。
3. **安全扫描 Agent** → 结合规则检测和 LLM 上下文分析，发现硬编码密钥、注入风险等。
4. **汇总 Agent** → 综合前三者输出，通过推理整合优先级，生成 Markdown 报告。

## 安装
pip install -r requirements.txt

## 配置
设置环境变量 `OPENAI_API_KEY`（或修改 config.py）

## 使用
python main.py sample.py

交互式：
python main.py  (粘贴代码，输入EOF结束)