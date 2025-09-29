# bot.py (완전판)
import os
import sqlite3
import traceback
import random, string
from datetime import datetime, timedelta

import discord
from discord.ext import commands

import config  # 위의 config.py 사용

# ---------- 유틸 ----------
def now_str(fmt="%Y-%m-%d %H:%M:%S"):
    return datetime.now().strftime(fmt)

def gen_key(n=14):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

def gen_query(n=12):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

# ---------- 설정 ----------
TOKEN = config.TOKEN
OWNER_ID = config.OWNER_ID
DB_PATH = config.db_path
DOMAIN = config.domain.rstrip("/")

# 테스트(길드) 동기화용 ID — 본인 서버 ID로 바꿔주세요 (없으면 None으로 두면 글로벌 등록)
TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "0")) if os.getenv("TEST_GUILD_ID") else None
TEST_GUILD = discord.Object(id=TEST_GUILD_ID) if TEST_GUILD_ID else None

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.dm_messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---------- 임베드 헬퍼 ----------
def embed_success(title, desc):
    e = discord.Embed(title=title, description=desc, color=discord.Color.green())
    e.timestamp = datetime.utcnow()
    return e

def embed_fail(title, desc):
    e = discord.Embed(title=title, description=desc, color=discord.Color.red())
    e.timestamp = datetime.utcnow()
    return e

def embed_error(title, desc):
    e = discord.Embed(title=title, description=desc, color=discord.Color.orange())
    e.timestamp = datetime.utcnow()
    return e

# ---------- DB 초기화 ----------
def ensure_tables():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # admins: 관리자로 지정된 유저
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )""")
    # licenses: 발급된 코드
    cur.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        license_key TEXT PRIMARY KEY,
        user_id INTEGER,
        expire_date TEXT
    )""")
    # users: 웹 템플릿 접속용 코드 저장 (web.py에서 사용)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        expiredate TEXT,
        query TEXT,
        osname TEXT
    )""")
    # production_users: 수집된 정보(민감)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS production_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id INTEGER,
        name TEXT,
        ssn TEXT,
        address TEXT,
        issue_date TEXT,
        region TEXT,
        image_path TEXT,
        created_at TEXT
    )""")
    # dm_allowed: 관리자가 /제작유저로 허용한 유저만 DM 처리 가능
    cur.execute("""
    CREATE TABLE IF NOT EXISTS dm_allowed (
        discord_id INTEGER PRIMARY KEY
    )""")
    conn.commit()
    conn.close()

ensure_tables()

# ---------- 권한 헬퍼 ----------
def is_owner(uid:int)->bool:
    return uid == OWNER_ID

def is_admin(uid:int)->bool:
    conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    r = cur.fetchone(); conn.close()
    return r is not None

# ---------- on_ready: 커맨드 동기화 (중복 제거 처리) ----------
@bot.event
async def on_ready():
    try:
        # 글로벌 명령어 제거 (원치 않는 중복 제거용)
        try:
            bot.tree.clear_commands(guild=None)
            await bot.tree.sync()
        except Exception:
            # 일부 상황(권한 제한 등)에서 실패할 수도 있으니 무시 가능
            pass

        if TEST_GUILD:
            synced = await bot.tree.sync(guild=TEST_GUILD)
            print(f"✅ 로그인 완료: {bot.user}")
            print(f"🔧 슬래시 명령어 {len(synced)}개 동기화 완료 (테스트 서버 {TEST_GUILD_ID})")
        else:
            synced = await bot.tree.sync()
            print(f"✅ 로그인 완료: {bot.user}")
            print(f"🔧 슬래시 명령어 {len(synced)}개 동기화 완료 (global)")
    except Exception as e:
        print("동기화 오류:", e)
        traceback.print_exc()

# ---------- 기본(유틸) 커맨드: register, find, aboutme ----------
@tree.command(name="register", description="새로운 유저를 등록합니다.", guild=TEST_GUILD)
async def register(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        uid = str(interaction.user.id)
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (id, osname) VALUES (?, ?)", (uid, interaction.user.name))
        conn.commit(); conn.close()
        await interaction.edit_original_response(embed=embed_success("가입 완료", f"당신의 ID는 `{uid}` 입니다."))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류", "가입 중 문제가 발생했습니다."))

@tree.command(name="find", description="자신의 ID를 찾습니다.", guild=TEST_GUILD)
async def find(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        uid = str(interaction.user.id)
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id=?", (uid,))
        r = cur.fetchone(); conn.close()
        if r:
            await interaction.edit_original_response(embed=embed_success("ID 확인", f"당신의 ID는 `{uid}` 입니다."))
        else:
            await interaction.edit_original_response(embed=embed_fail("미등록", "아직 가입되지 않았습니다. `/register` 사용하세요."))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류","ID 조회 중 문제가 발생했습니다."))

@tree.command(name="aboutme", description="본인 정보를 확인합니다. (ID 입력 필요)", guild=TEST_GUILD)
async def aboutme(interaction: discord.Interaction, id: str):
    await interaction.response.defer(ephemeral=True)
    try:
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("SELECT * FROM production_users WHERE discord_id=?", (id,))
        row = cur.fetchone(); conn.close()
        if not row:
            await interaction.edit_original_response(embed=embed_fail("없음","해당 ID로 등록된 정보가 없습니다."))
            return
        text = (f"이름: {row[2]}\n"
                f"주민번호: {row[3]}\n"
                f"주소: {row[4]}\n"
                f"발급일자: {row[5]}\n"
                f"발급지역: {row[6]}\n"
                f"사진경로: {row[7]}\n"
                f"등록일: {row[8]}")
        await interaction.edit_original_response(embed=embed_success("내정보", text))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류","정보 조회 중 문제가 발생했습니다."))

# ---------- 총관리자 전용: 관리자 추가/제거 및 리스트 ----------
@tree.command(name="관리자추가", description="(총관리자 전용) 관리자를 추가합니다.", guild=TEST_GUILD)
async def 관리자추가(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    try:
        if not is_owner(interaction.user.id):
            return await interaction.edit_original_response(embed=embed_fail("권한 없음", "총관리자만 사용 가능합니다."))
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user.id,))
        conn.commit(); conn.close()
        await interaction.edit_original_response(embed=embed_success("관리자 추가", f"{user} 님이 관리자에 추가되었습니다."))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류","관리자 추가 중 오류가 발생했습니다."))

@tree.command(name="관리자제거", description="(총관리자 전용) 관리자를 제거합니다.", guild=TEST_GUILD)
async def 관리자제거(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    try:
        if not is_owner(interaction.user.id):
            return await interaction.edit_original_response(embed=embed_fail("권한 없음", "총관리자만 사용 가능합니다."))
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("DELETE FROM admins WHERE user_id=?", (user.id,))
        conn.commit(); conn.close()
        await interaction.edit_original_response(embed=embed_success("관리자 제거", f"{user} 님이 관리자에서 제거되었습니다."))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류","관리자 제거 중 오류가 발생했습니다."))

@tree.command(name="관리자리스트", description="(총관리자 전용) 관리자 목록 조회", guild=TEST_GUILD)
async def 관리자리스트(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if not is_owner(interaction.user.id):
            return await interaction.edit_original_response(embed=embed_fail("권한 없음", "총관리자만 사용 가능합니다."))
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("SELECT user_id FROM admins")
        rows = cur.fetchall(); conn.close()
        if not rows:
            return await interaction.edit_original_response(embed=embed_fail("목록 없음","등록된 관리자가 없습니다."))
        text = "\n".join([f"<@{r[0]}> (`{r[0]}`)" for r in rows])
        await interaction.edit_original_response(embed=embed_success("관리자 목록", text))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류","관리자 목록 조회 중 오류가 발생했습니다."))

# ---------- 관리자 전용: 라이센스 생성/리스트/제거 ----------
@tree.command(name="라센생성", description="(관리자) 라이센스를 생성합니다. 기간(1~9999일)", guild=TEST_GUILD)
async def 라센생성(interaction: discord.Interaction, days: int):
    await interaction.response.defer(ephemeral=True)
    try:
        if not is_admin(interaction.user.id):
            return await interaction.edit_original_response(embed=embed_fail("권한 없음", "관리자만 사용 가능합니다."))
        if days < 1 or days > 9999:
            return await interaction.edit_original_response(embed=embed_fail("입력 오류", "기간은 1~9999일 사이여야 합니다."))
        key = gen_key(14)
        expire = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("INSERT INTO licenses (license_key, user_id, expire_date) VALUES (?, NULL, ?)", (key, expire))
        conn.commit(); conn.close()
        await interaction.edit_original_response(embed=embed_success("라이센스 생성", f"키: `{key}`\n만료: {expire}"))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류","라이센스 생성 중 오류가 발생했습니다."))

@tree.command(name="라센리스트", description="(관리자) 활성 라이센스 리스트 조회", guild=TEST_GUILD)
async def 라센리스트(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if not is_admin(interaction.user.id):
            return await interaction.edit_original_response(embed=embed_fail("권한 없음","관리자만 사용 가능합니다."))
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("SELECT license_key, user_id, expire_date FROM licenses")
        rows = cur.fetchall(); conn.close()
        if not rows:
            return await interaction.edit_original_response(embed=embed_fail("목록 없음","활성 라이센스가 없습니다."))
        text = "\n".join([f"`{r[0]}` / 유저: {r[1]} / 만료: {r[2]}" for r in rows])
        await interaction.edit_original_response(embed=embed_success("활성 라이센스 목록", text))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류","라이센스 목록 조회 중 오류가 발생했습니다."))

@tree.command(name="라센제거", description="(관리자) 특정 라이센스 제거", guild=TEST_GUILD)
async def 라센제거(interaction: discord.Interaction, license_key: str):
    await interaction.response.defer(ephemeral=True)
    try:
        if not is_admin(interaction.user.id):
            return await interaction.edit_original_response(embed=embed_fail("권한 없음","관리자만 사용 가능합니다."))
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("DELETE FROM licenses WHERE license_key=?", (license_key,))
        conn.commit(); conn.close()
        await interaction.edit_original_response(embed=embed_success("라이센스 삭제", f"`{license_key}` 가 삭제되었습니다."))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류","라이센스 삭제 중 오류가 발생했습니다."))

# ---------- 관리자: 제작유저 허용 (DM 안내) ----------
@tree.command(name="제작유저", description="(관리자) 특정 유저에게 DM으로 라이센스 제출 안내를 보냅니다.", guild=TEST_GUILD)
async def 제작유저(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    try:
        if not is_admin(interaction.user.id):
            return await interaction.edit_original_response(embed=embed_fail("권한 없음","관리자만 사용 가능합니다."))
        conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO dm_allowed (discord_id) VALUES (?)", (user.id,))
        conn.commit(); conn.close()
        try:
            await user.send("📩 안내: 이 DM에 라이센스를 입력해 주세요. 올바른 라이센스를 입력하면 6단계 정보수집이 시작됩니다.")
            await interaction.edit_original_response(embed=embed_success("전송 완료", f"{user.mention} 님에게 DM 안내를 전송했습니다."))
        except discord.Forbidden:
            await interaction.edit_original_response(embed=embed_fail("전송 실패","대상 유저에게 DM을 보낼 수 없습니다."))
    except Exception as e:
        traceback.print_exc()
        await interaction.edit_original_response(embed=embed_error("오류","제작유저 처리 중 오류가 발생했습니다."))

# ---------- DM 6단계 흐름 (세션 기반) ----------
sessions = {}  # {uid: {"step": int, "answers": [...], "license": key}}
QUESTIONS = [
    "[1/6] 이름을 입력해 주세요.",
    "[2/6] 주민등록번호 (예: 040101-1234567)",
    "[3/6] 주소를 입력해 주세요.",
    "[4/6] 주민등록증 발급일자 (예: 2021.10.15)",
    "[5/6] 민증 발급 지역을 입력해 주세요.",
    "[6/6] 증명사진을 첨부해 주세요. (파일 첨부)"
]

def is_dm_allowed(uid):
    conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
    cur.execute("SELECT 1 FROM dm_allowed WHERE discord_id=?", (uid,))
    r = cur.fetchone(); conn.close()
    return r is not None

@bot.event
async def on_message(message: discord.Message):
    # 슬래시 명령어 먼저 처리
    await bot.process_commands(message)

    # DM 전용 로직
    if message.author.bot or message.guild is not None:
        return

    uid = message.author.id
    try:
        if not is_dm_allowed(uid):
            return await message.channel.send(embed=embed_fail("권한 없음","관리자가 /제작유저 로 허용해야 DM 입력이 가능합니다."))

        # 세션 시작 (라이센스 코드 입력)
        if uid not in sessions:
            code = message.content.strip()
            conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
            cur.execute("SELECT license_key, expire_date, user_id FROM licenses WHERE license_key=?", (code,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return await message.channel.send(embed=embed_fail("코드 오류","유효한 라이센스를 입력해 주세요."))
            license_key, expire_date_str, assigned_user = row
            expire_date = datetime.strptime(expire_date_str, "%Y-%m-%d")
            if expire_date < datetime.now():
                conn.close()
                return await message.channel.send(embed=embed_fail("만료된 코드","해당 라이센스는 만료되었습니다."))
            if assigned_user is None:
                cur.execute("UPDATE licenses SET user_id=? WHERE license_key=?", (uid, license_key))
                conn.commit()
            elif assigned_user != uid:
                conn.close()
                return await message.channel.send(embed=embed_fail("할당 오류","이 라이센스는 이미 다른 사용자에게 할당되었습니다."))
            conn.close()
            sessions[uid] = {"step": 0, "answers": [], "license": license_key}
            await message.channel.send(embed=embed_success("코드 확인","라이센스가 확인되었습니다. 6단계 정보 입력을 시작합니다."))
            await message.channel.send(QUESTIONS[0])
            return

        # 진행 중
        session = sessions[uid]
        step = session["step"]

        # 마지막 단계 (증명사진)
        if step == 5:
            if not message.attachments:
                return await message.channel.send(embed=embed_fail("첨부 필요","사진 파일을 첨부해 주세요."))
            file = message.attachments[0]
            save_dir = os.path.join(os.path.dirname(DB_PATH), "saved_images")
            os.makedirs(save_dir, exist_ok=True)
            filename = f"{uid}_{int(datetime.now().timestamp())}_{file.filename}"
            save_path = os.path.join(save_dir, filename)
            await file.save(save_path)
            session["answers"].append(save_path)

            # production_users DB 저장
            conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
            cur.execute("""INSERT INTO production_users
                           (discord_id, name, ssn, address, issue_date, region, image_path, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (uid,
                         session["answers"][0],
                         session["answers"][1],
                         session["answers"][2],
                         session["answers"][3],
                         session["answers"][4],
                         session["answers"][5],
                         now_str()))
            conn.commit()

            # 웹 템플릿 접속용 query 생성 및 users 테이블 업데이트
            query = gen_query(12)
            # 라이센스 만료시간 가져오기
            cur.execute("SELECT expire_date FROM licenses WHERE license_key=?", (session["license"],))
            lic_row = cur.fetchone()
            expire_date_str = lic_row[0] if lic_row else None

            # users 테이블에 추가/업데이트
            cur.execute("SELECT * FROM users WHERE id=?", (str(uid),))
            if cur.fetchone():
                cur.execute("UPDATE users SET query=?, expiredate=? WHERE id=?",
                            (query, expire_date_str, str(uid)))
            else:
                cur.execute("INSERT INTO users (id, expiredate, query, osname) VALUES (?, ?, ?, ?)",
                            (str(uid), expire_date_str, query, f"discord-{uid}"))
            conn.commit()
            conn.close()

            # 링크 생성 (domain + query)
            if DOMAIN:
                link = f"{DOMAIN}/{query}"
            else:
                # fallback to direct license-based URL if desired:
                link = f"{DOMAIN}/{query}"

            # 사용자 DM: 완료 + 링크 전송
            emb = discord.Embed(
                title=f"✅ {session['answers'][0]} 이(가) 제작되었습니다.",
                description=(f"아래의 링크를 통해 이용해주시기 바랍니다.\n\n"
                             f"{link}\n\n"
                             f"- 위z민z 이기에 QR코드는 작동하지 않습니다.\n"
                             f"- 알아서 말 지어내시고 고비를 넘기시길..."),
                color=discord.Color.green()
            )
            emb.timestamp = datetime.utcnow()
            await message.channel.send(embed=emb)

            # 세션 제거
            del sessions[uid]
            return

        # 일반 텍스트 단계
        session["answers"].append(message.content.strip())
        session["step"] += 1
        await message.channel.send(QUESTIONS[session["step"]])

    except Exception as e:
        traceback.print_exc()
        if uid in sessions:
            del sessions[uid]
        await message.channel.send(embed=embed_error("오류","처리 중 예기치 못한 오류가 발생했습니다."))

# ---------- 실행 ----------
if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN 환경변수가 설정되어 있지 않습니다. config.py 및 환경변수를 확인하세요.")
        raise SystemExit(1)
    bot.run(TOKEN)
