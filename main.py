# -*- coding: utf-8 -*-
# main.py — PuzzleGold relay (Render-friendly)

import os, re, threading, logging
from typing import Optional
from flask import Flask
from telethon import events
from telethon.sessions import StringSession
from telethon import TelegramClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("puzzlegold")

# --------- ENV ---------
API_ID        = os.getenv("API_ID")          # بعداً واقعی می‌گذاری
API_HASH      = os.getenv("API_HASH")        # بعداً واقعی می‌گذاری
SESSION_STRING= os.getenv("SESSION_STRING")  # بعداً واقعی می‌گذاری
SOURCE        = os.getenv("SOURCE_CHANNEL", "shemshineh")
DEST          = os.getenv("DEST_CHANNEL", "puzzlegold")

RUN_USERBOT = bool(SESSION_STRING and API_ID and API_HASH)

# --------- Flask keepalive ---------
app = Flask(__name__)

@app.get("/")
def ok():
    return "PuzzleGold relay is running.", 200

def run_flask():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))

# --------- Text helpers ---------
def fa_num_to_int(s: str) -> Optional[int]:
    # تبدیل ارقام فارسی/عربی به انگلیسی و حذف جداکننده‌ها
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    cleaned = re.sub(r"[^\d]", "", s.translate(trans))
    return int(cleaned) if cleaned else None

def tweak_text(text: str) -> Optional[str]:
    # فقط پیام‌هایی که تیتر «ابشده خرد» دارند
    if not re.search(r"(?i)ابشده\s*خرد", text):
        return None

    out = text

    # هر مثقال → اولین «خرید» و کم کردن 460,000
    m_methqal = re.search(r"(هر\s*مثقال.*?)(خرید\s*:\s*[^0-9۰-۹]+)?([0-9۰-۹\.,]+)", out, flags=re.S)
    if m_methqal:
        amount = fa_num_to_int(m_methqal.group(3))
        if amount:
            amount -= 460000
            out = out.replace(m_methqal.group(3), f"{amount:,}")

    # هر گرم → اولین «خرید» و کم کردن 100,000
    m_gram = re.search(r"(هر\s*گرم.*?)(خرید\s*:\s*[^0-9۰-۹]+)?([0-9۰-۹\.,]+)", out, flags=re.S)
    if m_gram:
        amount = fa_num_to_int(m_gram.group(3))
        if amount:
            amount -= 100000
            out = out.replace(m_gram.group(3), f"{amount:,}")

    # جایگزینی لینک منبع با کانال مقصد
    out = re.sub(r"@shemshineh", "@puzzlegold", out, flags=re.I)

    return out

# --------- Telethon (اختیاری تا وقتی SESSION_STRING داری) ---------
client = None
if RUN_USERBOT:
    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)

    @client.on(events.NewMessage(chats=SOURCE))
    async def relay_handler(ev):
        txt = ev.message.message or ""
        new_txt = tweak_text(txt)
        if new_txt:
            try:
                await client.send_message(DEST, new_txt)
                log.info("Relayed a tweaked message.")
            except Exception as e:
                log.exception("Send failed: %s", e)
        else:
            log.info("Skipped (no 'ابشده خرد').")

def main():
    # Flask thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    if RUN_USERBOT:
        log.info("Starting Telethon client...")
        client.start()
        log.info("Userbot is running. Watching channel: @%s", SOURCE)
        client.run_until_disconnected()
    else:
        log.warning("SESSION_STRING/APIs not set. Only Flask is running.")
        t.join()

if __name__ == "__main__":
    main()
