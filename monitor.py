import requests
import pandas as pd
import sqlite3
import os
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HEADERS = {"User-Agent": "Mozilla/5.0"}
DB = "stock.db"

# === Telegram ===
def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
    except:
        print("Telegram 發送失敗")

# === DB ===
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS revenue (
        stock_id TEXT,
        date TEXT,
        revenue REAL
    )
    """)
    conn.commit()
    conn.close()

# === 抓資料 ===
def fetch_revenue(typek):
    url = "https://mops.twse.com.tw/mops/web/ajax_t21sc03"

    payload = {
        "encodeURIComponent": 1,
        "step": 1,
        "firstin": 1,
        "TYPEK": typek,
        "year": str(datetime.now().year - 1911),
        "month": str(datetime.now().month - 1)
    }

    try:
        res = requests.post(url, data=payload, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        tables = pd.read_html(res.text)
    except:
        return pd.DataFrame()

    dfs = []
    for t in tables:
        if "公司代號" in t.columns:
            dfs.append(t)

    return pd.concat(dfs) if dfs else pd.DataFrame()

# === 分析 ===
def analyze():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    df = pd.concat([
        fetch_revenue("sii"),
        fetch_revenue("otc")
    ])

    if df.empty:
        send("⚠️ 今日抓不到營收資料")
        return []

    results = []
    today = datetime.now().strftime("%Y-%m")

    for _, row in df.iterrows():
        try:
            stock_id = str(row["公司代號"])
            revenue = float(row["當月營收"])
            last_year = float(row["去年當月營收"])

            if last_year == 0:
                continue

            yoy = (revenue - last_year) / last_year * 100

            # 基本過濾
            if yoy < 25 or revenue < 1e8:
                continue

            # 歷史最大
            c.execute("SELECT MAX(revenue) FROM revenue WHERE stock_id=?", (stock_id,))
            max_rev = c.fetchone()[0]

            # 上月
            c.execute("""
                SELECT revenue FROM revenue
                WHERE stock_id=? ORDER BY date DESC LIMIT 1
            """, (stock_id,))
            last = c.fetchone()

            # 存資料
            c.execute(
                "INSERT INTO revenue VALUES (?,?,?)",
                (stock_id, today, revenue)
            )

            new_high = max_rev and revenue > max_rev
            growth = last and revenue > last[0]

            score = yoy
            if new_high:
                score += 50
            if growth:
                score += 20

            results.append({
                "id": stock_id,
                "yoy": yoy,
                "score": score
            })

        except:
            continue

    conn.commit()
    conn.close()

    return sorted(results, key=lambda x: x["score"], reverse=True)[:5]

# === 通知 ===
def notify(top5):
    if not top5:
        return

    today = datetime.now().strftime("%Y-%m-%d")

    msg = f"🚀 強勢股 Top5\n{today}\n\n"

    for i, s in enumerate(top5, 1):
        msg += f"{i}. {s['id']} | YoY {s['yoy']:.1f}%\n"

    send(msg)

# === 主程式 ===
if __name__ == "__main__":
    init_db()

    try:
        top5 = analyze()
        notify(top5)
    except Exception as e:
        send(f"❌ 系統錯誤: {str(e)}")
