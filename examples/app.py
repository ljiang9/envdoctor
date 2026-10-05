"""示例应用：故意包含缺失变量、空值变量等情况。"""
import os

db = os.environ["DATABASE_URL"]
key = os.environ["API_KEY"]            # 示例里为空，且没给默认值 -> 未设值
port = int(os.getenv("PORT", "8080"))  # 有默认值
stripe = os.environ["STRIPE_KEY"]      # 示例里没有 -> 缺失
level = os.getenv("LOG_LEVEL", "info") # 示例里为空，但有默认值 -> 不告警


def main():
    print(db, key, port, stripe, level)
