# -*- coding: utf-8 -*-
"""
SokootNet - نسخه مخصوص سرور 24 ساعته
توکن از Environment Variable خوانده می شود
"""
import urllib.request
import urllib.error
import json
import random
import time
import threading
import ssl
import html
import base64
import traceback
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

# ================== تنظیمات ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN ست نشده! توی Render بخش Environment Variables اضافه اش کن")

WEBAPP_URL = "https://sokootnet.netlify.app"
DONATE_URL = ""

API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""
REFRESH = 180
CONFIGS_PER_MSG = 5
MAX_MSG_LEN = 3800

SOURCES = [
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/All_Configs_Sub.txt",
    "https://raw.githubusercontent.com/0xRadikal/Free-v2ray-Configs/main/all/configs.txt",
    "https://raw.githubusercontent.com/MhdiTaheri/V2rayCollector/main/sub/mix",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/Server.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW_General.txt",
]

SUB_LINKS = [
    ("Epodonios", "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt"),
    ("0xRadikal", "https://raw.githubusercontent.com/0xRadikal/Free-v2ray-Configs/main/verified/configs_base64.txt"),
    ("MhdiTaheri", "https://raw.githubusercontent.com/MhdiTaheri/V2rayCollector/main/sub/mix"),
]

VALID_PROTOCOLS = ("vless://", "vmess://", "trojan://", "ss://", "hy2://", "tuic://")
PROTOCOL_NAMES = {
    "vless://": "VLESS", "vmess://": "VMESS", "trojan://": "TROJAN",
    "ss://": "SHADOWSOCKS", "hy2://": "HYSTERIA2", "tuic://": "TUIC",
}
config_pool = []
last_refresh = 0
offset = 0
refreshing = False
BOT_USERNAME = ""

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# ================== سرور سلامت برای Render ==================
def keep_alive():
    port = int(os.environ.get("PORT", "10000"))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            try:
                self.wfile.write("SokootNet is alive".encode("utf-8"))
            except Exception:
                pass
        def log_message(self, *args):
            return
    try:
        srv = HTTPServer(("0.0.0.0", port), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"Health server on port {port}")
    except Exception as e:
        print(f"Health server error: {e}")

# ================== ارتباط با تلگرام ==================
def tg(method, params=None, http_timeout=40):
    if params is None:
        params = {}
    try:
        body = json.dumps(params).encode("utf-8")
        req = urllib.request.Request(
            f"{API}/{method}", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=http_timeout, context=CTX) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        print(f"HTTP {e.code} در {method}: {detail}")
        return {}
    except Exception as e:
        print(f"خطای شبکه در {method}: {e}")
        return {}

# ================== دریافت کانفیگ‌ها ==================
def fetch_configs():
    global config_pool, last_refresh, refreshing
    raw = []
    ok_sources = 0
    for url in SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15, context=CTX) as resp:
                txt = resp.read().decode("utf-8", "ignore")
            if "://" not in txt and len(txt) > 80:
                try:
                    txt = base64.b64decode(txt).decode("utf-8", "ignore")
                except Exception:
                    pass
            raw.extend(txt.splitlines())
            ok_sources += 1
        except Exception:
            continue
    seen, uniq = set(), []
    for line in raw:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.lower().startswith(VALID_PROTOCOLS):
            continue
        if line in seen:
            continue
        seen.add(line)
        uniq.append(line)
    if uniq:
        config_pool = uniq
        last_refresh = time.time()
        print(f"{len(config_pool)} کانفیگ یکتا از {ok_sources} منبع دریافت شد")
    else:
        print("هیچ منبعی جواب نداد")
    refreshing = False

def refresh_async():
    global refreshing
    if refreshing:
        return
    refreshing = True
    threading.Thread(target=fetch_configs, daemon=True).start()

def refresher_loop():
    while True:
        time.sleep(REFRESH)
        refresh_async()

# ================== ارسال پیام ==================
def _send_raw(chat_id, text, keyboard, with_html):
    params = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if with_html:
        params["parse_mode"] = "HTML"
    if keyboard:
        params["reply_markup"] = {"inline_keyboard": keyboard}
    res = tg("sendMessage", params)
    if not res.get("ok") and with_html:
        return _send_raw(chat_id, text, keyboard, False)
    return res

def send_message(chat_id, text, keyboard=None):
    if len(text) <= MAX_MSG_LEN:
        return _send_raw(chat_id, text, keyboard, True)
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) + 2 > MAX_MSG_LEN:
            chunks.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    res = {}
    for i, chunk in enumerate(chunks):
        kb = keyboard if i == len(chunks) - 1 else None
        res = _send_raw(chat_id, chunk, kb, True)
    return res

def send_configs(chat_id, picks):
    header = f"🎲 <b>{len(picks)} کانفیگ آماده اتصال:</b>"
    body_parts = []
    for i, c in enumerate(picks, 1):
        proto = next((v for k, v in PROTOCOL_NAMES.items()
                      if c.lower().startswith(k)), "CONFIG")
        body_parts.append(f"<b>{i}.</b> <i>{proto}</i>\n<code>{html.escape(c, quote=False)}</code>")
    footer = "👆 کپی کن و توی v2rayNG یا Hiddify اضافه کن"
    send_message(chat_id, header + "\n\n" + "\n\n".join(body_parts) + "\n\n" + footer,
                 main_keyboard())

# ================== دکمه‌ها ==================
def main_keyboard():
    kb = [
        [
            {"text": "🎲 ۵ کانفیگ آماده", "callback_data": "random"},
            {"text": "🔗 سابسکریپشن", "callback_data": "subs"},
        ],
        [
            {"text": "📊 وضعیت", "callback_data": "status"},
            {"text": "❓ راهنما", "callback_data": "help"},
        ],
        [{"text": "🌐 اپ سکوت‌نت", "web_app": {"url": WEBAPP_URL}}],
    ]
    if BOT_USERNAME:
        share = (f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}"
                 f"&text=%F0%9F%9B%B0%EF%B8%8F%20%DA%A9%D8%A7%D9%86%D9%81%DB%8C%DA%AF%20"
                 f"%D8%B1%D8%A7%DB%8C%DA%AF%D8%A7%D9%86%20%D8%A8%DA%AF%DB%8C%D8%B1!%20%F0%9F%91%87")
        kb.append([{"text": "👥 دعوت دوستان", "url": share}])
    if DONATE_URL:
        kb.append([{"text": "☕ حمایت از سکوت‌نت", "url": DONATE_URL}])
    return kb

WELCOME = (
    "🌙 <b>به سکوت‌نت خوش اومدی!</b>\n"
    "<i>جایی که اینترنت، دوباره آزاده...</i>\n\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "🛰️ کانفیگ‌های رایگان و به‌روز V2Ray رو هر "
    "<b>۳ دقیقه</b> از معتبرترین منابع جمع می‌کنم.\n\n"
    "<b>📂 بخش‌ها — از دکمه‌های پایین انتخاب کن:</b>\n\n"
    "🎲 <b>۵ کانفیگ آماده</b> → پنج کانفیگ تصادفی برای اتصال فوری\n"
    "🔗 <b>سابسکریپشن</b> → لینک ساب که خودش کانفیگ‌ها رو آپدیت نگه می‌داره\n"
    "📊 <b>وضعیت</b> → آمار مخزن کانفیگ‌ها\n"
    "❓ <b>راهنما</b> → آموزش قدم‌به‌قدم اتصال\n"
    "🌐 <b>اپ سکوت‌نت</b> → سایت کامل، مستقیم داخل تلگرام!\n\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "✨ <i>سکوت‌کن... و آزاد فکر کن.</i>"
)

HELP_TEXT = (
    "❓ <b>راهنمای اتصال — قدم‌به‌قدم</b>\n\n"
    "<b>۱. برنامه رو نصب کن:</b>\n"
    "📱 اندروید → <b>v2rayNG</b> یا <b>Hiddify</b>\n"
    "📱 آیفون → <b>Streisand</b> یا <b>Hiddify</b>\n"
    "💻 ویندوز → <b>v2rayN</b> یا <b>Hiddify</b>\n\n"
    "<b>۲. کانفیگ بگیر:</b>\n"
    "روی «🎲 ۵ کانفیگ آماده» بزن، یکی رو کپی کن\n\n"
    "<b>۳. اضافه کن:</b>\n"
    "v2rayNG → دکمه + ← «Import from clipboard»\n\n"
    "<b>۴. وصل شو:</b>\n"
    "کانفیگ رو انتخاب کن و دکمه اتصال رو بزن ✅\n\n"
    "<b>💡 نکته:</b> اگه یه کانفیگ وصل نشد، دوباره «۵ کانفیگ آماده» بزن.\n\n"
    "⚡ برای راحتی بیشتر از <b>🔗 سابسکریپشن</b> استفاده کن."
)

# ================== پردازش پیام‌ها ==================
def handle_update(upd):
    global offset
    offset = upd["update_id"] + 1
    if "callback_query" in upd:
        cb = upd["callback_query"]
        msg = cb.get("message") or cb.get("inline_message")
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        if not msg:
            return
        chat_id = msg["chat"]["id"]
        print(f"دکمه زده شد: {cb.get('data', '')}")
        handle_command(chat_id, cb.get("data", ""))
        return
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    if not text:
        return
    print(f"پیام از {chat_id}: {text[:50]}")
    handle_command(chat_id, text.split("@")[0].lower())

def handle_command(chat_id, cmd):
    if cmd in ("/start", "start", "/start@bot"):
        send_message(chat_id, WELCOME, main_keyboard())
    elif cmd in ("random", "🎲 ۵ کانفیگ آماده", "🎲 کانفیگ تازه"):
        if not config_pool:
            send_message(chat_id, "⏳ دارم کانفیگ‌ها رو می‌گیرم... چند لحظه بعد دوباره بزن")
            refresh_async()
            return
        n = min(CONFIGS_PER_MSG, len(config_pool))
        send_configs(chat_id, random.sample(config_pool, n))
    elif cmd in ("subs", "🔗 سابسکریپشن", "🔗 لینک‌های ساب"):
        lines = ["🔗 <b>لینک‌های سابسکریپشن — یه بار اضافه کن، همیشه تازه:</b>\n"]
        for name, url in SUB_LINKS:
            lines.append(f"<b>{html.escape(name)}</b>:\n<code>{url}</code>\n")
        lines.append("📌 اضافه‌کردن توی v2rayNG:")
        lines.append("Subscription → + → لینک رو بچسبون → ذخیره → آپدیت")
        send_message(chat_id, "\n".join(lines), main_keyboard())
    elif cmd in ("status", "📊 وضعیت"):
        if last_refresh:
            age = int(time.time() - last_refresh)
            age_txt = f"{age // 60} دقیقه پیش" if age >= 60 else f"{age} ثانیه پیش"
        else:
            age_txt = "هنوز شروع نشده"
        send_message(chat_id,
            f"📊 <b>وضعیت سکوت‌نت</b>\n\n"
            f"📦 کانفیگ‌های یکتا: <b>{len(config_pool)}</b>\n"
            f"🔄 آخرین تازه‌سازی: <b>{age_txt}</b>\n"
            f"🌐 منابع: <b>{len(SOURCES)}</b>\n"
            f"⏱ دوره تازه‌سازی: هر {REFRESH // 60} دقیقه",
            main_keyboard())
    elif cmd in ("help", "❓ راهنما", "/help"):
        send_message(chat_id, HELP_TEXT, main_keyboard())
    else:
        send_message(chat_id, "🤔 متوجه نشدم — از دکمه‌های پایین انتخاب کن:", main_keyboard())

# ================== راه‌اندازی ==================
def setup_bot():
    tg("setMyCommands", {"commands": [
        {"command": "start",   "description": "🚀 منوی اصلی"},
        {"command": "random",  "description": "🎲 ۵ کانفیگ آماده"},
        {"command": "subs",    "description": "🔗 سابسکریپشن"},
        {"command": "status",  "description": "📊 وضعیت"},
        {"command": "help",    "description": "❓ راهنمای اتصال"},
    ]})
    tg("setChatMenuButton",
       {"menu_button": {"type": "web_app", "text": "🌐 اپ سکوت‌نت", "web_app": {"url": WEBAPP_URL}}})
    tg("deleteWebhook", {"drop_pending_updates": False})
    print(f"دکمه اپ فعال شد → {WEBAPP_URL}")

# ================== حلقه اصلی ==================
def main():
    global BOT_USERNAME
    if not BOT_TOKEN:
        print("BOT_TOKEN پیدا نشد. خروج.")
        while True:
            time.sleep(60)
    print("بات در حال روشن شدن...")
    keep_alive()
    me = {}
    for attempt in range(1, 6):
        me = tg("getMe", http_timeout=20)
        if me.get("ok"):
            break
        print(f"اتصال برقرار نشد... تلاش {attempt}/5 — ۵ ثانیه صبر")
        time.sleep(5)
    if not me.get("ok"):
        print("۵ بار تلاش شد و جواب نیومد.")
        return
    info = me["result"]
    BOT_USERNAME = info.get("username", "")
    print(f"بات «{info.get('first_name', '?')}» (@{BOT_USERNAME}) آنلاین شد!")
    setup_bot()
    refresh_async()
    threading.Thread(target=refresher_loop, daemon=True).start()
    while True:
        try:
            res = tg("getUpdates", {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message", "callback_query"],
            }, http_timeout=45)
            if not res:
                time.sleep(3)
                continue
            if not res.get("ok"):
                desc = res.get("description", "")
                print("تلگرام:", desc)
                if "Conflict" in desc or "409" in desc:
                    print("دو نسخه از بات همزمان اجرا شده!")
                time.sleep(3)
                continue
            for upd in res.get("result", []):
                try:
                    handle_update(upd)
                except Exception:
                    print("خطا در پردازش پیام:")
                    traceback.print_exc()
        except KeyboardInterrupt:
            print("بات خاموش شد")
            break
        except Exception:
            traceback.print_exc()
            time.sleep(3)

if __name__ == "__main__":
    main()
