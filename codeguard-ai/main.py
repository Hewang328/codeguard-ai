import sys
from agents import build_workflow

def review_code(code: str, filename: str = "reviewed_file.py") -> str:
    """执行完整的审查流程，返回报告"""
    workflow = build_workflow()
    initial_state = {
        "code": code,
        "filename": filename,
        "ast_output": "",
        "metrics": {},
        "structure_issues": [],
        "style_issues": [],
        "security_issues": [],
        "final_report": ""
    }
    # 同步执行
    final_state = workflow.invoke(initial_state)
    return final_state["final_report"]

if __name__ == "__main__":
    # 示例：从参数或标准输入读取代码
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            code = f.read()
        filename = sys.argv[1]
    else:
        print("用法: python main.py <代码文件路径>")
        print("或者交互式输入代码 (以 'EOF' 结束):")
        lines = []
        while True:
            line = input()
            if line.strip() == 'EOF':
                break
            lines.append(line)
        code = '\n'.join(lines)
        filename = "stdin_input.py"

    report = review_code(code, filename)
    print("\n========== 审查报告 ==========\n")
    print(report)
    print("\n==============================\n")