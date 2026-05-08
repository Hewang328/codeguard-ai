import os

# 从环境变量读取，更安全
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-key-here")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")  # 可选，用于自动评论
MODEL_NAME = "gpt-4o-mini"  # 性价比高，可换 gpt-4o
MAX_TOKENS = 2000
TEMPERATURE = 0.1  # 输出更确定