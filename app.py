from functools import lru_cache, wraps
import sqlite3
import time
from threading import Thread
import random
import uuid
from flask import Flask, g, jsonify, redirect, render_template, request, url_for, abort, flash
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import yfinance as yf

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key-change-this-in-production!'
socketio = SocketIO(app, cors_allowed_origins="*")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'

DATABASE = "database.db"

LINE_ACCESS_TOKEN = "cafLEB/WAFPZWbauNQYoZDPeaKg7kyAQaLAazFHEZgkA5KDTfvesiqkWWk9rGbRBFWgX7uNSVfFhhqXQ7BpupntpAQ5+lpMGhbEadfYm+mvQtof2jVbXgfg0hr0c29Gl0ZHbVwOkireoDwDZJvGenAdB04t89/1O/w1cDnyilFU="

LANGUAGES = {
    "en": {
        "dashboard": "Dashboard",
        "watchlist": "Watchlist",
        "alerts": "Alerts",
        "notifications": "Notifications",
        "ai_analysis": "AI Analysis",
        "settings": "Settings",
        "logout": "Logout",
        "search_placeholder": "Search ticker or company — e.g. NVDA",
        "dash_title": "Stock Intelligence, at a glance.",
        "dash_subtitle": "AI-Powered Real-Time Stock Monitoring & Predictive Analytics",
        "create_alert": "Create Alert",
        "total_watchlist": "TOTAL WATCHLIST",
        "active_tracked_assets": "Active tracked assets",
        "active_alerts": "ACTIVE ALERTS",
        "real_time_triggers": "Real-time triggers",
        "bullish_signals": "BULLISH SIGNALS",
        "ai_positive_momentum": "AI positive momentum",
        "bearish_signals": "BEARISH SIGNALS",
        "ai_negative_momentum": "AI negative momentum",
        "my_watchlist_portfolio": "My Watchlist Portfolio",
        "real_time_tracking_matrix": "Real-time tracking asset matrix",
        "th_symbol": "SYMBOL",
        "th_company": "COMPANY",
        "th_price": "PRICE",
        "th_change": "CHANGE",
        "th_ema_trend": "EMA TREND",
        "th_ai_signal": "AI SIGNAL",
        "websocket_connected": "Live WebSocket Connected",
    },
    "th": {
        "dashboard": "หน้าหลัก",
        "watchlist": "รายการเฝ้าดู",
        "alerts": "แจ้งเตือน",
        "notifications": "ประวัติการแจ้งเตือน",
        "ai_analysis": "วิเคราะห์ AI",
        "settings": "ตั้งค่าระบบ",
        "logout": "ออกจากระบบ",
        "search_placeholder": "ค้นหาชื่อหุ้นหรือบริษัท เช่น NVDA",
        "dash_title": "ข้อมูลเชิงลึกหุ้นแบบเรียลไทม์",
        "dash_subtitle": "ระบบติดตามและวิเคราะห์แนวโน้มหุ้นอัจฉริยะด้วย AI",
        "create_alert": "สร้างการแจ้งเตือน",
        "total_watchlist": "รายการเฝ้าดูทั้งหมด",
        "active_tracked_assets": "สินทรัพย์ที่กำลังติดตาม",
        "active_alerts": "การแจ้งเตือนที่เปิดใช้งาน",
        "real_time_triggers": "เงื่อนไขเรียลไทม์",
        "bullish_signals": "สัญญาณขาขึ้น (BULLISH)",
        "ai_positive_momentum": "โมเมนตัมเชิงบวกจาก AI",
        "bearish_signals": "สัญญาณขาลง (BEARISH)",
        "ai_negative_momentum": "โมเมนตัมเชิงลบจาก AI",
        "my_watchlist_portfolio": "พอร์ตรายการเฝ้าดูของฉัน",
        "real_time_tracking_matrix": "ตารางติดตามสถานะสินทรัพย์แบบเรียลไทม์",
        "th_symbol": "สัญลักษณ์",
        "th_company": "บริษัท",
        "th_price": "ราคา",
        "th_change": "เปลี่ยนแปลง",
        "th_ema_trend": "แนวโน้ม EMA",
        "th_ai_signal": "สัญญาณ AI",
        "websocket_connected": "เชื่อมต่อ WebSocket แล้ว",
    }
}

@app.context_processor
def inject_lang_and_globals():
    current_lang = "en"
    if current_user.is_authenticated:
        try:
            db = get_db()
            row = db.execute("SELECT value FROM settings WHERE key = 'language'").fetchone()
            if row and row["value"] in ["en", "th"]:
                current_lang = row["value"]
        except Exception:
            pass
            
    def get_text(key):
        return LANGUAGES.get(current_lang, LANGUAGES["en"]).get(key, key)
        
    return {
        "current_lang": current_lang,
        "t": get_text
    }

class User(UserMixin):
    def __init__(self, id, username, email, is_admin):
        self.id = str(id)
        self.username = username
        self.email = email
        self.is_admin = bool(is_admin)

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    cursor = db.execute("SELECT id, username, email, is_admin FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return User(row["id"], row["username"], row["email"], row["is_admin"])
    return None

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403) 
        return f(*args, **kwargs)
    return decorated_function

def get_db():
  db = getattr(g, "_database", None)
  if db is None:
    db = g._database = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
  return db

@app.teardown_appcontext
def close_connection(exception):
  db = getattr(g, "_database", None)
  if db is not None:
    db.close()

def init_db():
  with app.app_context():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT 0
        )
    """)
    db.execute("CREATE TABLE IF NOT EXISTS stocks (symbol TEXT PRIMARY KEY, name TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS watchlist (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, alert_type TEXT, target REAL, status TEXT, created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    db.execute("CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, type TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS line_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            line_id TEXT,
            token TEXT UNIQUE,
            status TEXT DEFAULT 'PENDING'
        )
    """)

    admin_check = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if admin_check == 0:
        hashed_pw = generate_password_hash("admin123", method='scrypt')
        db.execute("INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)",
                   ("Administrator", "admin@stock.com", hashed_pw, 1))

    cursor = db.execute("SELECT COUNT(*) FROM stocks")
    if cursor.fetchone()[0] == 0:
      initial_stocks = [
          ("NVDA", "NVIDIA Corporation"),
          ("AAPL", "Apple Inc."),
          ("MSFT", "Microsoft Corporation"),
          ("TSLA", "Tesla Inc."),
          ("AMZN", "Amazon.com Inc."),
      ]
      db.executemany("INSERT INTO stocks VALUES (?, ?)", initial_stocks)
      db.executemany("INSERT INTO watchlist (symbol) VALUES (?)", [("NVDA",), ("AAPL",), ("TSLA",)])
      db.executemany("INSERT INTO alerts (symbol, alert_type, target, status) VALUES (?, ?, ?, ?)", [
          ("NVDA", "PRICE ABOVE", 150.0, "PENDING"),
          ("TSLA", "EMA GOLDEN CROSS", 0.0, "ACTIVE"),
      ])
      db.executemany("INSERT INTO notifications (message, type) VALUES (?, ?)", [
          ("System initialized with live Yahoo Finance API", "System"),
          ("Bullish signal monitored via live data", "AI Signal"),
      ])
    db.commit()

@lru_cache(maxsize=64)
def _fetch_yf_data_cached(symbol, period, cache_time_block):
  ticker = yf.Ticker(symbol)
  hist = None
  live_current_price = None
  try:
    if hasattr(ticker, "fast_info") and ticker.fast_info.last_price:
      live_current_price = float(ticker.fast_info.last_price)
  except Exception:
    pass

  try:
    if period == "1d":
      hist = ticker.history(period="1d", interval="1m")
      if hist is None or hist.empty:
        hist = ticker.history(period="5d", interval="15m")
    elif period == "5d":
      hist = ticker.history(period="5d", interval="15m")
    elif period == "1mo":
      hist = ticker.history(period="1mo", interval="1d")
    elif period == "6mo":
      hist = ticker.history(period="6mo", interval="1d")
    elif period == "ytd":
      hist = ticker.history(period="ytd", interval="1d")
    elif period == "1y":
      hist = ticker.history(period="1y", interval="1d")
    elif period == "5y":
      hist = ticker.history(period="5y", interval="1wk")
    else:
      hist = ticker.history(period="1y", interval="1d")
  except Exception as e:
    print(f"Primary fetch error for {symbol} ({period}): {e}")

  if hist is None or hist.empty or "Close" not in hist.columns:
    try:
      hist = ticker.history(period=period)
    except Exception as e:
      print(f"Fallback fetch error for {symbol}: {e}")

  if hist is None or hist.empty or "Close" not in hist.columns:
    return get_fallback_data(symbol)

  try:
    current_price = live_current_price if live_current_price else float(hist["Close"].iloc[-1])
    prev_close = float(hist["Close"].iloc[-2] if len(hist) > 1 else current_price)
    change = round(((current_price - prev_close) / prev_close) * 100, 2)

    ema50 = round(float(hist["Close"].ewm(span=50, adjust=False).mean().iloc[-1]), 2) if len(hist) >= 50 else round(current_price * 0.98, 2)
    ema100 = round(float(hist["Close"].ewm(span=100, adjust=False).mean().iloc[-1]), 2) if len(hist) >= 100 else round(current_price * 0.96, 2)
    ema200 = round(float(hist["Close"].ewm(span=200, adjust=False).mean().iloc[-1]), 2) if len(hist) >= 200 else round(current_price * 0.94, 2)

    recent_history = hist["Close"].tolist()
    if period == "1d":
      chart_labels = [d.strftime("%H:%M") for d in hist["Close"].index]
    elif period in ["5d", "1mo"]:
      chart_labels = [d.strftime("%d %b %H:%M") if period == "5d" else d.strftime("%d %b") for d in hist["Close"].index]
    else:
      chart_labels = [d.strftime("%Y-%m-%d") for d in hist["Close"].index]

    chart_prices = [round(p, 2) for p in recent_history]

    return {
        "symbol": symbol,
        "name": symbol,
        "price": round(current_price, 2),
        "change": change,
        "ema50": ema50,
        "ema100": ema100,
        "ema200": ema200,
        "chart_labels": chart_labels,
        "chart_prices": chart_prices,
    }
  except Exception as e:
    print(f"Data processing error for {symbol}: {e}")
    return get_fallback_data(symbol)

def get_live_stock_data(symbol, period="1y"):
  cache_block = int(time.time() // 10)
  return _fetch_yf_data_cached(symbol, period, cache_block)

def get_fallback_data(symbol):
  return {
      "symbol": symbol,
      "name": symbol,
      "price": 100.0,
      "change": 0.0,
      "ema50": 98.0,
      "ema100": 95.0,
      "ema200": 90.0,
      "chart_labels": ["Day 1", "Day 2", "Day 3", "Day 4", "Current"],
      "chart_prices": [100, 100, 100, 100, 100],
  }

def analyze_stock(price, ema50, ema100, ema200):
  if not isinstance(ema50, (int, float)) or not isinstance(ema100, (int, float)) or not isinstance(ema200, (int, float)):
    return "NEUTRAL", "Insufficient data for full EMA calculation."
  if price > ema50 > ema100 > ema200:
    return "BULLISH", "Price is above EMA50, EMA100 and EMA200."
  elif price < ema50 < ema100 < ema200:
    return "BEARISH", "Price is below EMA50, EMA100 and EMA200."
  return "NEUTRAL", "Price action is consolidating between EMAs."

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        login_input = request.form.get("username")
        password = request.form.get("password")
        db = get_db()
        user_row = db.execute("SELECT * FROM users WHERE username = ? OR email = ?", (login_input, login_input)).fetchone()
        
        if user_row and check_password_hash(user_row["password"], password):
            user_obj = User(user_row["id"], user_row["username"], user_row["email"], user_row["is_admin"])
            login_user(user_obj)
            flash("เข้าสู่ระบบสำเร็จ", "success")
            if user_obj.is_admin:
                return redirect(url_for("admin_page"))
            return redirect(url_for("dashboard"))
        else:
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "danger")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        
        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ? OR username = ?", (email, username)).fetchone()
        if existing:
            flash("อีเมลหรือชื่อผู้ใช้นี้ถูกใช้งานแล้ว", "danger")
            return redirect(url_for("register_page"))
        
        hashed_pw = generate_password_hash(password, method='scrypt')
        db.execute("INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)",
                   (username, email, hashed_pw, 0))
        db.commit()
        flash("สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ", "success")
        return redirect(url_for("login_page"))
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("ออกจากระบบเรียบร้อย", "info")
    return redirect(url_for("login_page"))

@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
  db = get_db()
  stock_rows = db.execute("SELECT symbol FROM stocks").fetchall()
  watchlist_rows = db.execute("SELECT symbol FROM watchlist").fetchall()

  stocks = [get_live_stock_data(row["symbol"], "1y") for row in stock_rows]
  watchlist = [get_live_stock_data(row["symbol"], "1y") for row in watchlist_rows]

  market_symbols = {
      "S&P 500": "^GSPC",
      "NASDAQ": "^IXIC",
      "DOW JONES": "^DJI",
      "BTC": "BTC-USD",
      "ETH": "ETH-USD"
  }
  
  market_overview = []
  for name, symbol in market_symbols.items():
    data = get_live_stock_data(symbol, "1y")
    market_overview.append({
        "name": name,
        "symbol": symbol,
        "price": data["price"],
        "change": data["change"],
        "chart_prices": data["chart_prices"]
    })

  active_alerts = db.execute("SELECT COUNT(*) FROM alerts WHERE status != 'DELETED'").fetchone()[0]

  bullish_count = 0
  bearish_count = 0
  for s in stocks:
    signal, _ = analyze_stock(s["price"], s["ema50"], s["ema100"], s["ema200"])
    if signal == "BULLISH":
      bullish_count += 1
    elif signal == "BEARISH":
      bearish_count += 1

  return render_template(
      "dashboard.html",
      stocks=stocks,
      watchlist=watchlist,
      market_overview=market_overview,
      total_watchlist=len(watchlist),
      active_alerts=active_alerts,
      bullish_count=bullish_count,
      bearish_count=bearish_count,
  )

@app.route("/api/stocks")
@login_required
def api_stocks():
  db = get_db()
  stock_rows = db.execute("SELECT symbol FROM stocks").fetchall()
  stocks_data = []
  for row in stock_rows:
    s = get_live_stock_data(row["symbol"], "1y")
    signal, _ = analyze_stock(s["price"], s["ema50"], s["ema100"], s["ema200"])
    s["ai_signal"] = signal
    s["trend"] = "Up" if s["change"] >= 0 else "Down"
    stocks_data.append(s)
  return jsonify(stocks_data)

@app.route("/api/search_stocks")
@login_required
def api_search_stocks():
  query = request.args.get("q", "").strip()
  if not query:
    return jsonify([])
  results = []
  try:
    search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(search_url, headers=headers, timeout=5)
    data = response.json()
    if 'quotes' in data and data['quotes']:
      for q in data['quotes']:
        sym = q.get('symbol')
        if sym and q.get('quoteType') in ['EQUITY', 'ETF', 'MUTUALFUND']:
          results.append({
              "symbol": sym,
              "name": q.get('shortname') or q.get('longname') or sym,
              "exchange": q.get('exchange', 'GLOBAL'),
              "type": 'ETF' if q.get('quoteType') == 'ETF' else 'หุ้นสามัญ'
          })
  except Exception as e:
    print(f"Search API error: {e}")
  return jsonify(results)

@app.route("/watchlist")
@login_required
def watchlist_page():
  db = get_db()
  items_rows = db.execute("SELECT symbol FROM watchlist").fetchall()
  all_stocks_rows = db.execute("SELECT symbol FROM stocks").fetchall()
  items = [get_live_stock_data(row["symbol"], "1y") for row in items_rows]
  all_stocks = [dict(row) for row in all_stocks_rows]
  
  alerts_rows = db.execute("SELECT symbol, alert_type, target FROM alerts WHERE status != 'DELETED'").fetchall()
  alert_map = {a["symbol"]: f"{a['alert_type']}: {a['target']}" for a in alerts_rows}

  enriched = []
  for s in items:
    signal, _ = analyze_stock(s["price"], s["ema50"], s["ema100"], s["ema200"])
    enriched.append({
        **s, 
        "trend": "Up" if s["change"] >= 0 else "Down", 
        "ai_signal": signal,
        "alert_status": alert_map.get(s["symbol"], "NO ALERT")
    })
  return render_template("watchlist.html", watchlist=enriched, all_stocks=all_stocks)

@app.route("/watchlist/add", methods=["POST"])
@login_required
def watchlist_add():
  symbol = request.form.get("symbol", "").upper().strip()
  db = get_db()
  if symbol:
    if not db.execute("SELECT * FROM stocks WHERE symbol = ?", (symbol,)).fetchone():
      db.execute("INSERT INTO stocks (symbol, name) VALUES (?, ?)", (symbol, symbol))
    if not db.execute("SELECT * FROM watchlist WHERE symbol = ?", (symbol,)).fetchone():
      db.execute("INSERT INTO watchlist (symbol) VALUES (?)", (symbol,))
      db.commit()
  return redirect(url_for("watchlist_page"))

@app.route("/watchlist/delete/<symbol>")
@login_required
def watchlist_delete(symbol):
  db = get_db()
  db.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
  db.commit()
  return redirect(url_for("watchlist_page"))

@app.route("/stocks/<symbol>")
@login_required
def stock_detail(symbol):
  period = request.args.get("period", "1y").lower()
  stock = get_live_stock_data(symbol, period if period in ["1d", "5d", "1mo", "6mo", "ytd", "1y", "5y"] else "1y")
  signal, reason = analyze_stock(stock["price"], stock["ema50"], stock["ema100"], stock["ema200"])
  
  golden_cross = stock["ema50"] > stock["ema200"]
  death_cross = stock["ema50"] < stock["ema200"]

  # --- AI Intelligence & Forecast Dynamic Integration ---
  price = stock['price']
  change = stock['change']
  ema50 = stock['ema50']
  
  is_bullish = change >= 0 and price >= ema50
  condition = "Uptrend" if is_bullish else "Downtrend"
  momentum = "Strong" if abs(change) > 1.5 else "Moderate"
  
  short_low = round(price * 0.99, 2)
  short_high = round(price * 1.03, 2)
  med_low = round(price * 0.96, 2)
  med_high = round(price * 1.08, 2)
  
  ai_data = {
      "confidence": 78 if is_bullish else 62,
      "condition": condition,
      "momentum": momentum,
      "summary": f"AI ประเมินว่าหุ้น {symbol} อยู่ในช่วง{'ขาขึ้น' if is_bullish else 'ขาลง'} โดยราคาปัจจุบันเคลื่อนตัวสัมพันธ์กับค่าเฉลี่ยหลัก ความผันผวนอยู่ในระดับ {momentum.lower()} เหมาะแก่การติดตามกรอบราคาใกล้ชิด",
      "short_target": f"{short_low}–{short_high}",
      "med_target": f"{med_low}–{med_high}",
      "signal": "BULLISH" if is_bullish else "BEARISH"
  }

  return render_template(
      "stocks.html", 
      stock=stock, 
      signal=signal, 
      reason=reason, 
      current_period=period,
      golden_cross=golden_cross,
      death_cross=death_cross,
      ai=ai_data
  )

@app.route("/stocks")
@login_required
def stocks_page():
  db = get_db()
  stock_rows = db.execute("SELECT symbol FROM stocks").fetchall()
  stocks = [get_live_stock_data(row["symbol"], "1y") for row in stock_rows]
  return render_template("stocks_list.html", stocks=stocks)

@app.route("/alerts", methods=["GET", "POST"])
@login_required
def alerts_page():
  db = get_db()
  if request.method == "POST":
    symbol = request.form.get("symbol")
    alert_type = request.form.get("alert_type")
    target = float(request.form.get("target") or 0)
    db.execute("INSERT INTO alerts (symbol, alert_type, target, status) VALUES (?, ?, ?, ?)", (symbol, alert_type, target, "PENDING"))
    db.commit()
    return redirect(url_for("alerts_page"))
  alerts = db.execute("SELECT * FROM alerts").fetchall()
  stocks = db.execute("SELECT symbol FROM stocks").fetchall()
  return render_template("alerts.html", alerts=alerts, stocks=stocks)

@app.route("/alerts/delete/<int:id>")
@login_required
def alert_delete(id):
  db = get_db()
  db.execute("DELETE FROM alerts WHERE id = ?", (id,))
  db.commit()
  return redirect(url_for("alerts_page"))

@app.route("/notifications")
@login_required
def notifications_page():
  db = get_db()
  notifications = db.execute("SELECT * FROM notifications ORDER BY id DESC").fetchall()
  return render_template("notifications.html", notifications=notifications)

@app.route("/ai")
@login_required
def ai_analysis_page():
  db = get_db()
  stocks = [get_live_stock_data(row["symbol"], "1y") for row in db.execute("SELECT symbol FROM stocks").fetchall()]
  results = []
  for s in stocks:
    signal, reason = analyze_stock(s["price"], s["ema50"], s["ema100"], s["ema200"])
    results.append({"symbol": s["symbol"], "name": s["name"], "price": s["price"], "signal": signal, "reason": reason})
  return render_template("ai_analysis.html", results=results)

@app.route("/line", methods=["GET", "POST"])
@login_required
def line_page():
  db = get_db()
  if request.method == "POST":
    for key in ["price_alert", "ema_alert", "bullish_save", "bullish_signal", "bearish_signal", "daily_summary"]:
      db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, "1" if request.form.get(key) else "0"))
    db.commit()
    return redirect(url_for("line_page"))
  settings = {row["key"]: row["value"] for row in db.execute("SELECT * FROM settings").fetchall()}
  return render_template("line.html", settings=settings)

@app.route("/profile")
@login_required
def profile_page():
  return render_template("profile.html")

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
  db = get_db()
  if request.method == "POST":
    lang = request.form.get("language")
    line_token = request.form.get("line_token")
    
    if lang:
      db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("language", lang))
    if line_token is not None:
      db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("line_notify_token", line_token))
      
    db.commit()
    flash("บันทึกการตั้งค่าเรียบร้อยแล้ว", "success")
    return redirect(url_for("settings_page"))
    
  conn = db.execute("SELECT * FROM line_connections WHERE user_id = ?", (current_user.id,)).fetchone()
  settings = {row["key"]: row["value"] for row in db.execute("SELECT * FROM settings").fetchall()}
  return render_template("settings.html", settings=settings, conn=conn)

@app.route("/settings/generate_token", methods=["POST"])
@login_required
def generate_line_token():
    db = get_db()
    while True:
        token = "STK-" + uuid.uuid4().hex[:8].upper()
        exists = db.execute("SELECT id FROM line_connections WHERE token = ?", (token,)).fetchone()
        if not exists:
            break
            
    db.execute("""
        INSERT INTO line_connections (user_id, token, status) 
        VALUES (?, ?, 'PENDING')
        ON CONFLICT(user_id) DO UPDATE SET token = ?, status = 'PENDING'
    """, (current_user.id, token, token))
    db.commit()
    
    flash("สร้าง LINE Token สำเร็จ กรุณานำไปส่งใน LINE OA", "success")
    return redirect(url_for("settings_page"))

def send_line_message(reply_token, message_text):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message_text}]
    }
    try:
        requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending LINE message: {e}")

@app.route("/line/webhook", methods=["GET", "POST"])
def line_webhook():
    if request.method == "GET":
        return jsonify({"status": "ready"}), 200
        
    data = request.json
    events = data.get("events", [])
    
    for event in events:
        if event["type"] == "message" and event["message"]["type"] == "text":
            text_received = event["message"]["text"].strip()
            line_user_id = event["source"]["userId"]
            reply_token = event.get("replyToken")
            
            db = get_db()
            conn = db.execute("SELECT * FROM line_connections WHERE token = ? AND status = 'PENDING'", (text_received,)).fetchone()
            
            if conn:
                db.execute("UPDATE line_connections SET line_id = ?, status = 'CONNECTED' WHERE id = ?", (line_user_id, conn["id"]))
                db.commit()
                if reply_token:
                    send_line_message(reply_token, "✅ ผูกบัญชีสำเร็จ! ตอนนี้คุณจะได้รับแจ้งเตือนหุ้นเฉพาะคุณผ่านแชทนี้แล้วครับ")
            else:
                already_connected = db.execute("SELECT * FROM line_connections WHERE line_id = ? AND status = 'CONNECTED'", (line_user_id,)).fetchone()
                if already_connected and reply_token:
                    send_line_message(reply_token, "ℹ️ บัญชี LINE นี้ได้ทำการผูกกับระบบไว้เรียบร้อยแล้วครับ")
                elif reply_token:
                    send_line_message(reply_token, "❌ Token ไม่ถูกต้องหรือหมดอายุ กรุณาสร้าง Token ใหม่จากหน้าตั้งค่าเว็บไซต์")
                
    return jsonify({"status": "ok"}), 200

@app.route("/admin")
@admin_required
def admin_page():
  db = get_db()
  total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
  active_users = total_users 
  active_alerts = db.execute("SELECT COUNT(*) FROM alerts WHERE status != 'DELETED'").fetchone()[0]
  notifications_sent = db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
  
  users_raw = db.execute("SELECT id, username, email, is_admin FROM users").fetchall()
  users_list = []
  
  for u in users_raw:
      if u["email"] == "somchaipochana@icloud.com":
          status_text = "No Active"
      else:
          status_text = "Active" if u["email"] else "No Active"
      
      watchlist_rows = db.execute("SELECT symbol FROM watchlist").fetchall()
      watchlist_items = [row["symbol"] for row in watchlist_rows]
      
      alerts_rows = db.execute("SELECT symbol, alert_type, target FROM alerts WHERE status != 'DELETED'").fetchall()
      alerts_items = [f"{a['symbol']} ({a['alert_type']}: {a['target']})" for a in alerts_rows]

      users_list.append({
          "id": u["id"],
          "email": u["email"],
          "username": u["username"],
          "status": status_text,
          "watchlist_count": len(watchlist_items),
          "watchlist_items": watchlist_items,
          "alerts_count": len(alerts_items),
          "alerts_items": alerts_items,
          "created_at": "-"
      })
  
  return render_template(
      "admin.html",
      total_users=total_users,
      active_users=active_users,
      active_alerts=active_alerts,
      notifications_sent=notifications_sent,
      users_list=users_list
  )

@app.route("/admin/edit-user/<int:user_id>", methods=["POST"])
@admin_required
def admin_edit_user(user_id):
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")
    
    if new_password:
        if new_password != confirm_password:
            flash("รหัสผ่านใหม่และยืนยันรหัสผ่านไม่ตรงกัน", "danger")
            return redirect(url_for("admin_page"))
            
        hashed_pw = generate_password_hash(new_password, method='scrypt')
        db = get_db()
        db.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_pw, user_id))
        db.commit()
        flash("เปลี่ยนรหัสผ่านผู้ใช้งานสำเร็จ", "success")
    else:
        flash("ไม่มีการเปลี่ยนแปลงรหัสผ่าน", "info")
        
    return redirect(url_for("admin_page"))

@app.route("/admin/delete-user/<int:user_id>")
@admin_required
def admin_delete_user_shortcut(user_id):
    return admin_delete_user(user_id)

@app.route("/admin/users/delete/<int:user_id>")
@admin_required
def admin_delete_user(user_id):
    if int(current_user.id) == user_id:
        flash("คุณไม่สามารถลบบัญชีตัวเองขณะใช้งานอยู่ได้", "danger")
        return redirect(url_for("admin_page"))
    
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("ลบผู้ใช้งานสำเร็จ", "success")
    return redirect(url_for("admin_page"))

@app.route("/admin/users/toggle_admin/<int:user_id>")
@admin_required
def admin_toggle_role(user_id):
    db = get_db()
    user = db.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        new_status = 0 if user["is_admin"] else 1
        db.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_status, user_id))
        db.commit()
        flash("ปรับเปลี่ยนสิทธิ์ผู้ใช้สำเร็จ", "success")
    return redirect(url_for("admin_page"))

@app.route("/admin/health")
@admin_required
def admin_health_page():
  return render_template("system_health.html")

@app.route("/api/system_health")
@admin_required
def api_system_health():
  db_status = "HEALTHY"
  try:
    get_db().execute("SELECT 1")
  except Exception:
    db_status = "UNAVAILABLE"

  market_status = "HEALTHY"
  try:
    res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1m&range=1d", timeout=3)
    if res.status_code != 200:
      market_status = "DEGRADED"
  except Exception:
    market_status = "UNAVAILABLE"

  return jsonify({
      "api_server": "HEALTHY",
      "database": db_status,
      "market_data": market_status,
      "scheduler": "RUNNING",
      "line_service": "READY",
      "ai_service": "READY"
  })

def background_stock_stream():
  while True:
    time.sleep(1)
    try:
      with app.app_context():
        db = get_db()
        symbols = [row["symbol"] for row in db.execute("SELECT symbol FROM watchlist").fetchall()]
        if not symbols:
          continue
        live_data = []
        for sym in symbols:
          s = get_live_stock_data(sym, "1y")
          signal, _ = analyze_stock(s["price"], s["ema50"], s["ema100"], s["ema200"])
          live_data.append({
              "symbol": s["symbol"], "name": s["name"], "price": s["price"],
              "change": s["change"], "ema50": s["ema50"], "ema200": s["ema200"], "ai_signal": signal
          })
        socketio.emit('stock_update', live_data)
    except Exception as e:
      print(f"Background stream error: {e}")

@socketio.on('connect')
def handle_connect():
  print("Client connected via WebSocket")

if __name__ == "__main__":
  init_db()
  thread = Thread(target=background_stock_stream)
  thread.daemon = True
  thread.start()
  socketio.run(app, debug=True, port=5000)