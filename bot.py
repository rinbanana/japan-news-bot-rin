import os
import json
import hashlib
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

SENT_FILE = "sent_news.json"
MAX_NEWS = 5
HOURS_LIMIT = 24

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=%E3%82%AA%E3%83%B3%E3%83%A9%E3%82%A4%E3%83%B3%E3%82%AB%E3%82%B8%E3%83%8E+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=%E3%82%AA%E3%83%B3%E3%82%AB%E3%82%B8+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=%E3%82%AA%E3%83%B3%E3%82%AB%E3%82%B8+%E9%80%AE%E6%8D%95+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=%E3%82%AA%E3%83%B3%E3%82%AB%E3%82%B8+%E8%A6%8F%E5%88%B6+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=%E3%82%AA%E3%83%B3%E3%83%A9%E3%82%A4%E3%83%B3%E3%82%AB%E3%82%B8%E3%83%8E+%E6%91%98%E7%99%BA+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=Japan+online+casino+when:1d&hl=en&gl=US&ceid=US:en",
]

KEYWORDS = [
    "オンラインカジノ",
    "オンカジ",
    "違法カジノ",
    "賭博",
    "ギャンブル",
    "逮捕",
    "摘発",
    "規制",
    "接続遮断",
    "削除要請",
    "online casino",
    "igaming",
    "gambling",
    "casino",
    "japan",
]

def load_sent():
    if not os.path.exists(SENT_FILE):
        return set()
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_sent(sent):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent)[-500:], f, ensure_ascii=False, indent=2)

def make_id(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(" ", strip=True)

def translate_to_ru(text):
    if not text:
        return "Нет текста для перевода."
    try:
        return GoogleTranslator(source="auto", target="ru").translate(text[:4500])
    except Exception:
        return "Не удалось перевести автоматически."

def parse_date(entry):
    raw = entry.get("published") or entry.get("updated")
    if not raw:
        return None, "Дата не указана"

    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        jst = dt.astimezone(timezone(timedelta(hours=9)))
        pretty = jst.strftime("%Y-%m-%d %H:%M JST")
        return dt.astimezone(timezone.utc), pretty
    except Exception:
        return None, raw

def is_fresh(published_dt):
    if not published_dt:
        return False
    now = datetime.now(timezone.utc)
    return now - published_dt <= timedelta(hours=HOURS_LIMIT)

def is_relevant(title, summary):
    combined = f"{title} {summary}".lower()
    return any(k.lower() in combined for k in KEYWORDS)

def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

def main():
    sent = load_sent()
    new_count = 0

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries[:10]:
            title = clean_html(entry.get("title", ""))
            summary = clean_html(entry.get("summary", ""))
            link = entry.get("link", "").strip()

            published_dt, published_pretty = parse_date(entry)

            if not title or not link:
                continue

            if not is_fresh(published_dt):
                continue

            if not is_relevant(title, summary):
                continue

            news_id = make_id(title + link)

            if news_id in sent:
                continue

            title_ru = translate_to_ru(title)
            summary_ru = translate_to_ru(summary)

            message = f"""🇯🇵 JAPAN iGAMING NEWS

📅 Дата публикации:
{published_pretty}

📰 Оригинал:
{title}

🇷🇺 Перевод:
{title_ru}

━━━━━━━━━━━━

🇯🇵 Описание:
{summary[:900] if summary else "Описание отсутствует."}

🇷🇺 Перевод описания:
{summary_ru[:1100]}

🔗 Источник:
{link}
"""

            send_telegram(message)
            sent.add(news_id)
            new_count += 1

            if new_count >= MAX_NEWS:
                break

        if new_count >= MAX_NEWS:
            break

    if new_count == 0:
        send_telegram("За последние 24 часа новых новостей по Japan iGaming / online casino не найдено.")

    save_sent(sent)

if __name__ == "__main__":
    main()
