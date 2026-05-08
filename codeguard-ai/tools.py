import ast
import re

def parse_python_ast(code: str) -> str:
    """解析给定Python代码的AST结构"""
    try:
        tree = ast.parse(code)
        return ast.dump(tree, indent=2)
    except SyntaxError as e:
        return f"Syntax error: {e}"

def count_lines(code: str) -> dict:
    """统计有效代码行数与注释行数"""
    lines = code.split('\n')
    total = len(lines)
    comments = sum(1 for line in lines if line.strip().startswith('#'))
    return {"total_lines": total, "comment_lines": comments}

def find_imports(code: str) -> list:
    """提取所有 import 语句"""
    pattern = r'^(?:from\s+\S+\s+)?import\s+\S+'
    return re.findall(pattern, code, re.MULTILINE)

def check_hardcoded_secrets(code: str) -> list:
    """简单的硬编码密钥检测"""
    patterns = {
        'API_KEY': r'(?i)(api[_-]?key|apikey)\s*=\s*["\'][^"\']+["\']',
        'PASSWORD': r'(?i)password\s*=\s*["\'][^"\']+["\']',
    }
    issues = []
    for secret_type, pattern in patterns.items():
        for match in re.finditer(pattern, code):
            issues.append(f"可能硬编码{secret_type}的行: {match.group()}")
    return issues