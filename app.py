from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from apscheduler.schedulers.background import BackgroundScheduler
from linebot import LineBotApi
from linebot.models import TextSendMessage
from datetime import datetime, date
from functools import wraps
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

app = Flask(__name__)

# 1. 設定密鑰與資料庫
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

database_url = os.environ.get('DATABASE_URL')
if database_url:
    # 修正 Render 的 postgres 格式
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 2. 初始化插件
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# 3. LINE 設定
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")

# --- 【關鍵補強】這段一定要加，否則雲端資料庫會是空的導致 500 錯誤 ---
with app.app_context():
    db.create_all()
# -----------------------------------------------------------

# ── 資料模型 ──────────────────────────────────────────────

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    records = db.relationship("Record", backref="user", lazy=True, cascade="all, delete-orphan")

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    desc = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    cat = db.Column(db.String(50), nullable=False)
    income = db.Column(db.Boolean, default=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today)
    record_time = db.Column(db.String(5), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ── 登入驗證裝飾器 ────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "請先登入"}), 401
        return f(*args, **kwargs)
    return decorated

# ── 頁面路由 ──────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return render_template("index.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

# ── API：帳號 ────────────────────────────────────────────

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "帳號密碼不得為空"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "帳號已存在"}), 400
    pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    user = User(username=username, password_hash=pw_hash)
    db.session.add(user)
    db.session.commit()
    session["user_id"] = user.id
    session["username"] = user.username
    return jsonify({"ok": True})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get("username", "")).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, data.get("password", "")):
        return jsonify({"error": "帳號或密碼錯誤"}), 401
    session["user_id"] = user.id
    session["username"] = user.username
    return jsonify({"ok": True})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
@login_required
def me():
    return jsonify({"username": session.get("username")})

# ── API：記帳 ────────────────────────────────────────────

@app.route("/api/records", methods=["GET"])
@login_required
def get_records():
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    q = Record.query.filter_by(user_id=session["user_id"])
    if year and month:
        from sqlalchemy import extract
        q = q.filter(
            extract("year", Record.record_date) == year,
            extract("month", Record.record_date) == month
        )
    records = q.order_by(Record.record_date.desc(), Record.created_at.desc()).all()
    return jsonify([{
        "id": r.id,
        "desc": r.desc,
        "amount": r.amount,
        "cat": r.cat,
        "income": r.income,
        "date": r.record_date.strftime("%Y-%m-%d"),
        "time": r.record_time,
    } for r in records])

@app.route("/api/records", methods=["POST"])
@login_required
def add_record():
    data = request.json
    try:
        record_date = datetime.strptime(data["date"], "%Y-%m-%d").date()
    except Exception:
        record_date = date.today()
    r = Record(
        user_id=session["user_id"],
        desc=data.get("desc", "記錄"),
        amount=float(data.get("amount", 0)),
        cat=data.get("cat", "其他"),
        income=bool(data.get("income", False)),
        record_date=record_date,
        record_time=data.get("time", "00:00"),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify({"id": r.id})

@app.route("/api/records/<int:record_id>", methods=["DELETE"])
@login_required
def delete_record(record_id):
    r = Record.query.filter_by(id=record_id, user_id=session["user_id"]).first()
    if not r:
        return jsonify({"error": "找不到紀錄"}), 404
    db.session.delete(r)
    db.session.commit()
    return jsonify({"ok": True})

# ── LINE 月底推播 ────────────────────────────────────────

def send_monthly_summary():
    if not LINE_TOKEN or not LINE_USER_ID:
        return
    today = date.today()
    year, month = today.year, today.month
    from sqlalchemy import extract
    records = Record.query.filter(
        extract("year", Record.record_date) == year,
        extract("month", Record.record_date) == month
    ).all()
    income = sum(r.amount for r in records if r.income)
    expense = sum(r.amount for r in records if not r.income)
    balance = income - expense
    msg = (
        f"📊 {year}/{month} 月份財務摘要\n"
        f"──────────────\n"
        f"💰 收入：${income:,.0f}\n"
        f"💸 支出：${expense:,.0f}\n"
        f"{'✅' if balance >= 0 else '⚠️'} 結餘：${balance:,.0f}\n"
        f"──────────────\n"
        f"記帳 App 自動推播"
    )
    line_bot_api = LineBotApi(LINE_TOKEN)
    line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text=msg))

# ── 排程器（每月最後一天 20:00 推播）────────────────────

scheduler = BackgroundScheduler()
scheduler.add_job(
    send_monthly_summary,
    trigger="cron",
    day="last",
    hour=20,
    minute=0,
    id="monthly_summary"
)
scheduler.start()

# ── 啟動 ─────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=False)
