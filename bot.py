import os
import json
import hashlib
import requests
import feedparser
from deep_translator import GoogleTranslator

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

SENT_FILE = "sent_news.json"

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=%E3%82%AA%E3%83%B3%E3%83%A9%E3%82%A4%E3%83%B3%E3%82%AB%E3%82%B8%E3%83%8E+%E6%97%A5%E6%9C%AC&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=%E6%97%A5%E6%9C%AC+%E3%82%AB%E3%82%B8%E3%83%8E+%E8%A6%8F%E5%88%B6&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=%E3%82%AA%E3%83%B3%E3%82%AB%E3%82%B8+%E9%80%AE%E6%8D%95&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=Japan+online+casino+regulation&hl=en&gl=US&ceid=US:en",
]

KEYWORDS = [
    "オンラインカジノ",
    "オンカジ",
    "カジノ",
    "ギャンブル",
    "賭博",
    "違法",
    "逮捕",
    "規制",
    "暗号資産",
    "仮想通貨",
    "online casino",
    "igaming",
    "gambling",
    "casino",
    "Japan",
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
        json.dump(list(sent)[-300:], f, ensure_ascii=False, indent=2)

def make_id(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def translate_to_ru(text):
    try:
        return GoogleTranslator(source="auto", target="ru").translate(text[:4500])
    except Exception:
        return "Не удалось перевести автоматически."

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

def is_relevant(title, summary):
    combined = f"{title} {summary}".lower()
    return any(k.lower() in combined for k in KEYWORDS)

def main():
    sent = load_sent()
    new_count = 0

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries[:8]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            link = entry.get("link", "").strip()
            published = entry.get("published", "Дата не указана")

            if not title or not link:
                continue

            if not is_relevant(title, summary):
                continue

            news_id = make_id(title + link)

            if news_id in sent:
                continue

            title_ru = translate_to_ru(title)
            summary_ru = translate_to_ru(summary) if summary else "Краткое описание отсутствует."

            message = f"""🇯🇵 JAPAN iGAMING NEWS

📅 Дата публикации:
{published}

📰 Оригинал:
{title}

🇷🇺 Перевод:
{title_ru}

━━━━━━━━━━━━

🇯🇵 Описание / оригинал:
{summary[:1000] if summary else "Описание отсутствует."}

🇷🇺 Описание / перевод:
{summary_ru[:1200]}

🔗 Источник:
{link}
"""

            send_telegram(message)
            sent.add(news_id)
            new_count += 1

            if new_count >= 5:
                break

        if new_count >= 5:
            break

    if new_count == 0:
        send_telegram("Сегодня новых новостей по Japan iGaming / online casino пока не найдено.")

    save_sent(sent)

if __name__ == "__main__":
    main()
