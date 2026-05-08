from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from config import OPENAI_API_KEY, MODEL_NAME, MAX_TOKENS, TEMPERATURE
from tools import parse_python_ast, count_lines, find_imports, check_hardcoded_secrets

# 全局 LLM 实例
llm = ChatOpenAI(
    openai_api_key=OPENAI_API_KEY,
    model_name=MODEL_NAME,
    max_tokens=MAX_TOKENS,
    temperature=TEMPERATURE
)

# 状态定义
class ReviewState(TypedDict):
    code: str
    filename: str
    ast_output: str
    metrics: dict
    structure_issues: List[str]
    style_issues: List[str]
    security_issues: List[str]
    final_report: str

# ---------- Agent 1: 结构分析 ----------
def structure_agent(state: ReviewState) -> ReviewState:
    code = state["code"]
    ast_out = parse_python_ast(code)
    metrics = count_lines(code)
    imports = find_imports(code)

    prompt = ChatPromptTemplate.from_template(
        """你是一名资深软件架构师。请根据以下AST结构、代码行数统计和导入包列表，
分析这段代码的架构合理性、模块划分以及是否存在明显的设计问题。
AST:
{ast}
行数统计: {metrics}
导入包: {imports}
代码:
{code}
请给出简洁的要点列表，每条一个潜在问题或优点。若无问题请回答'OK'。"""
    )
    messages = prompt.format_messages(ast=ast_out, metrics=metrics, imports=imports, code=code[:1500])
    response = llm.invoke(messages)
    issues = [line.strip("- ") for line in response.content.split('\n') if line.strip().startswith('-')]
    state["ast_output"] = ast_out
    state["metrics"] = metrics
    state["structure_issues"] = issues if issues else ["结构无明显问题"]
    return state

# ---------- Agent 2: 代码规范 ----------
def style_agent(state: ReviewState) -> ReviewState:
    code = state["code"]
    prompt = ChatPromptTemplate.from_template(
        """你是PEP8代码规范专家，并遵循Google风格指南。请检查以下Python代码是否符合：
1. 合理的空行与缩进
2. 命名约定（蛇形命名、大写常量）
3. 过长行（>120字符）
4. 文档字符串缺失
5. 复杂表达式应拆分
代码:
{code}
返回要点列表，每条一个违规项，若无则返回'OK'。"""
    )
    response = llm.invoke(prompt.format_messages(code=code[:2000]))
    issues = [line.strip("- ") for line in response.content.split('\n') if line.strip().startswith('-')]
    state["style_issues"] = issues if issues else ["风格完全符合规范"]
    return state

# ---------- Agent 3: 安全扫描 ----------
def security_agent(state: ReviewState) -> ReviewState:
    code = state["code"]
    # 先用规则做静态检测
    static_issues = check_hardcoded_secrets(code)
    prompt = ChatPromptTemplate.from_template(
        """你是应用安全专家。基于以下静态分析发现的问题和完整代码，进行安全审查，重点关注：
- SQL注入风险（如拼接SQL语句）
- XSS风险（如未转义的用户输入）
- 不安全的反序列化（如pickle）
- 弱随机数生成
已有静态发现: {static}
代码:
{code}
请返回安全风险列表，每条包含风险类型和位置描述。若无风险返回'OK'。"""
    )
    response = llm.invoke(prompt.format_messages(static=static_issues, code=code[:2000]))
    issues = [line.strip("- ") for line in response.content.split('\n') if line.strip().startswith('-')]
    if static_issues:
        issues.extend(static_issues)
    state["security_issues"] = issues if issues else ["未发现安全风险"]
    return state

# ---------- Agent 4: 汇总与报告生成 ----------
def summary_agent(state: ReviewState) -> ReviewState:
    prompt = ChatPromptTemplate.from_template(
        """你是技术主管，现在需要整合三个方面的代码审查结果，形成一份统一的审查报告。
报告格式要求：标题、总体评价、结构问题、风格问题、安全问题、改进建议优先级排序。

文件名: {filename}
代码行数: {metrics}

结构分析:
{structure}

风格检查:
{style}

安全扫描:
{security}

请生成完整的Markdown格式报告。"""
    )
    response = llm.invoke(prompt.format_messages(
        filename=state["filename"],
        metrics=state["metrics"],
        structure="\n".join(state["structure_issues"]),
        style="\n".join(state["style_issues"]),
        security="\n".join(state["security_issues"]),
    ))
    state["final_report"] = response.content
    return state

# 构建 LangGraph 工作流
def build_workflow():
    workflow = StateGraph(ReviewState)

    # 添加节点
    workflow.add_node("structure", structure_agent)
    workflow.add_node("style", style_agent)
    workflow.add_node("security", security_agent)
    workflow.add_node("summary", summary_agent)

    # 设置流程：结构 → 风格 → 安全 → 汇总（支持并行可优化，这里展示顺序长链推理）
    workflow.set_entry_point("structure")
    workflow.add_edge("structure", "style")
    workflow.add_edge("style", "security")
    workflow.add_edge("security", "summary")
    workflow.add_edge("summary", END)

    return workflow.compile()