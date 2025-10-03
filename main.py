# -*- coding: utf-8 -*-
# main.py — PuzzleGold userbot relay for Render
# Relays only "آبشده خرد/ابشده خرد" messages from CHANNEL_A to CHANNEL_B,
# edits first "خرید" after "هر مثقال" (-460,000) and first after "هر گرم" (-100,000),
# and replaces links @shemshineh -> @puzzlegold (configurable via env).

import os
import re
import threading
import logging
from typing import Optional

from flask import Flask
from telethon import events
from telethon.sessions import StringSession
from telethon import TelegramClient

# ---------------------------- Logging ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("puzzlegold")

# ------------------------- Keep-alive web -------------------------
app = Flask(__name__)

@app.get("/")
def home():
    return "puzzlegold relay running", 200

def run_web():
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# --------------------------- Config -------------------------------
API_ID    = int(os.environ["API_ID"])
API_HASH  = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]  # باید از قبل تولید و در Env بگذاری

CHANNEL_A = os.environ.get("CHANNEL_A", "@shemshineh")
CHANNEL_B = os.environ.get("CHANNEL_B", "@puzzlegold")

# کسورات
DEDUCT_MESGHAL = 460_000   # هر مثقال → اولین «خرید»
DEDUCT_GRAM    = 100_000   # هر گرم   → اولین «خرید»

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
EN_DIGITS = "0123456789"

def fa_to_en(text: str) -> str:
    """تبدیل ارقام فارسی/عربی به انگلیسی + نرمال‌سازی جداکننده‌ها و کالن‌ها"""
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    # digits
    for i, d in enumerate(FA_DIGITS):
        text = text.replace(d, EN_DIGITS[i])
    for i, d in enumerate(arabic_digits):
        text = text.replace(d, EN_DIGITS[i])
    # separators
    text = (text
            .replace("٬", ",")   # Arabic thousands separator
            .replace("،", ",")   # Persian comma
            .replace("’", "'")
            .replace("：", ":")   # full-width colon
            )
    return text

def en_to_fa_digits(text: str) -> str:
    out = []
    for ch in text:
        if "0" <= ch <= "9":
            out.append(FA_DIGITS[ord(ch) - ord("0")])
        else:
            out.append(ch)
    return "".join(out)

def format_int_fa(n: int) -> str:
    """فرمت با جداکننده هزاران و ارقام فارسی"""
    s = f"{n:,}"  # 12,345,678
    return en_to_fa_digits(s)

def replace_links(text: str, src_username: str, dst_username: str) -> str:
    """تعویض تمام ارجاعات از کانال مبدا به کانال مقصد"""
    src = src_username.lstrip("@")
    dst = dst_username if dst_username.startswith("@") else f"@{dst_username}"
    variants = [
        f"@{src}",
        f"t.me/{src}",
        f"http://t.me/{src}",
        f"https://t.me/{src}",
    ]
    for v in variants:
        text = text.replace(v, dst)
    return text

def replace_section_buy(original_text: str, section_keywords, deduct_amount: int) -> str:
    """
    از اولین رخداد یکی از section_keywords به بعد،
    اولین الگوی «خرید : عدد» را پیدا می‌کنیم و deduct می‌زنیم (فقط یک بار).
    """
    t_en = fa_to_en(original_text)
    # locate section start
    idx = -1
    for kw in section_keywords:
        p = t_en.find(kw)
        if p != -1 and (idx == -1 or p < idx):
            idx = p
    if idx == -1:
        return original_text  # section not found

    head, tail = t_en[:idx], t_en[idx:]
    # pattern: خرید : 12,345,678
    m = re.search(r"(خرید)\s*[::]?\s*([0-9,]+)", tail)
    if not m:
        return original_text

    old_num = int(m.group(2).replace(",", ""))
    new_num = max(0, old_num - deduct_amount)
    replacement = f"{m.group(1)} : {new_num:,}"

    tail_new = tail[:m.start()] + replacement + tail[m.end():]
    t_new = head + tail_new

    # فقط ارقام را فارسی کن (متن فارسی حفظ می‌شود)
    return en_to_fa_digits(t_new)

def should_process(text: Optional[str]) -> bool:
    if not text:
        return False
    # قبول هر دو املا: آبشده/ابشده
    needles = ("آبشده خرد", "ابشده خرد")
    return any(n in text for n in needles)

def process_message_text(text: str) -> str:
    """ویرایش متن طبق منطق کسب‌وکار و تعویض لینک‌ها"""
    # هر مثقال → -460k
    text = replace_section_buy(
        text, section_keywords=["هر مثقال", "هرمثقال"], deduct_amount=DEDUCT_MESGHAL
    )
    # هر گرم/هرگرم → -100k
    text = replace_section_buy(
        text, section_keywords=["هر گرم", "هرگرم"], deduct_amount=DEDUCT_GRAM
    )
    # تعویض لینک‌ها
    text = replace_links(text, src_username=CHANNEL_A, dst_username=CHANNEL_B)
    return text

# ----------------------- Telethon client --------------------------
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

@client.on(events.NewMessage(chats=[CHANNEL_A]))
async def handler(event):
    try:
        text = event.raw_text or ""
        if not should_process(text):
            return
        new_text = process_message_text(text)
        if new_text.strip():
            await client.send_message(CHANNEL_B, new_text)
            log.info("Relayed a processed message to %s", CHANNEL_B)
    except Exception as e:
        log.exception("Error processing message: %s", e)

async def on_startup():
    try:
        me = await client.get_me()
        log.info("Logged in as %s (%s)", me.first_name, me.id)
        # warm up entities (optional)
        await client.get_entity(CHANNEL_A)
        await client.get_entity(CHANNEL_B)
        log.info("Watching %s → %s", CHANNEL_A, CHANNEL_B)
    except Exception as e:
        log.exception("Startup error: %s", e)

# ----------------------------- Run --------------------------------
if __name__ == "__main__":
    log.info("Starting PuzzleGold relay…")
    client.loop.run_until_complete(on_startup())
    client.run_until_disconnected()
