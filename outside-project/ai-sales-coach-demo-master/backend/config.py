import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

load_dotenv(ROOT_DIR / ".env")
load_dotenv(BASE_DIR / ".env")

# Qwen / DashScope
OPENAI_API_KEY = (
    os.getenv("QWEN_API_KEY")
    or os.getenv("DASHSCOPE_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or ""
)
OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_CHAT = "qwen-plus"
MODEL_SCORE = "qwen-max"
AI_MODE = os.getenv("AI_MODE", "real").lower()
AI_DAILY_LIMIT_PER_USER = int(os.getenv("AI_DAILY_LIMIT_PER_USER", "30"))
AI_DAILY_LIMIT_PER_IP = int(os.getenv("AI_DAILY_LIMIT_PER_IP", "80"))

# SQLite
DB_PATH = os.getenv("DB_PATH", "training_demo.db")
AUTO_SEED_DEMO = os.getenv("AUTO_SEED_DEMO", "1") == "1"

# Auth
MANAGE_TOKEN_HEADER = "Manage-Token"
TOKEN_EXPIRE_HOURS = 72
