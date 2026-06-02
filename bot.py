import os
import json
import hashlib
import re
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
    "https://news.google.com/rss/search?q=オンラインカジノ+日本+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンカジ+日本+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+逮捕+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+規制+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+摘発+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+接続遮断+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+削除要請+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+決済+when:1d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+暗号資産+when:1d&hl=ja&gl=JP&ceid=JP:ja",
]

KEYWORDS = [
    "オンラインカジノ", "オンカジ", "違法カジノ", "賭博", "ギャンブル",
    "逮捕", "摘発", "規制", "接続遮断", "削除要請", "決済",
    "暗号資産", "仮想通貨", "カジノサイト", "カジノアプリ"
]

CATEGORY_RULES = {
    "🚨 Аресты / расследования": ["逮捕", "摘発", "書類送検", "容疑", "警察"],
    "⚖️ Регулирование": ["規制", "違法", "接続遮断", "削除要請", "総務省", "政府"],
    "💳 Платежи": ["決済", "送金", "銀行", "クレジット", "入金", "出金"],
    "₿ Крипто": ["暗号資産", "仮想通貨", "ビットコイン", "crypto"],
    "📈 Affiliate / Marketing": ["広告", "アフィリエイト", "宣伝", "SNS", "インフルエンサー"],
}

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

def clean_text(text):
    text = clean_html(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

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
        return dt.astimezone(timezone.utc), jst.strftime("%Y-%m-%d %H:%M JST")
    except Exception:
        return None, raw

def is_fresh(published_dt):
    if not published_dt:
        return False
    return datetime.now(timezone.utc) - published_dt <= timedelta(hours=HOURS_LIMIT)

def is_relevant(title, summary):
    combined = f"{title} {summary}".lower()
    return any(k.lower() in combined for k in KEYWORDS)

def detect_category(text):
    for category, words in CATEGORY_RULES.items():
        if any(word.lower() in text.lower() for word in words):
            return category
    return "🎰 Online Casino / General"

def fetch_article_text(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = " ".join(paragraphs)
        text = clean_text(text)

        if len(text) < 200:
            return ""

        return text[:3000]
    except Exception:
        return ""

def make_summary_ru(title_ru, article_ru):
    text = article_ru if article_ru and article_ru != "Не удалось перевести автоматически." else title_ru
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    summary = " ".join(sentences[:3]).strip()
    return summary[:900] if summary else title_ru

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
            title = clean_text(entry.get("title", ""))
            summary = clean_text(entry.get("summary", ""))
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

            article_jp = fetch_article_text(link)
            source_text = article_jp if article_jp else summary

            title_ru = translate_to_ru(title)
            article_ru = translate_to_ru(source_text)
            short_summary = make_summary_ru(title_ru, article_ru)

            category = detect_category(f"{title} {summary} {article_jp}")

            message = f"""🇯🇵 JAPAN iGAMING NEWS

📅 {published_pretty}

🏷 Категория:
{category}

📰 Оригинал:
{title}

🇷🇺 Заголовок:
{title_ru}

📌 Краткая выжимка:
{short_summary}

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
        send_telegram("За последние 24 часа новых новостей по японскому online casino / iGaming не найдено.")

    save_sent(sent)

if __name__ == "__main__":
    main()
