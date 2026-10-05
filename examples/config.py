"""配置模块：变量名拼写错误。"""
import os

# 注意：这里把 DATABASE_URL 拼成了 DATABSE_URL
dsn = os.getenv("DATABSE_URL")
