# config.py
import os

TOKEN = os.getenv("DISCORD_TOKEN")            # Render / 로컬 env에 설정
OWNER_ID = int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID") else None
db_path = os.getenv("DB_PATH", "DB/database.db")
domain = os.getenv("DOMAIN", "https://govr24.store")  # 당신 도메인
