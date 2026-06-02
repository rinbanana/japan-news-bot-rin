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
MAX_NEWS = 10
HOURS_LIMIT = 48

GOOGLE_RSS_FEEDS = [
    "https://news.google.com/rss/search?q=オンラインカジノ+日本+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンカジ+日本+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンライン賭博+日本+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=カジノサイト+日本+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=カジノアプリ+日本+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=海外カジノ+日本+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+逮捕+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+規制+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+摘発+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+接続遮断+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+削除要請+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+決済+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+暗号資産+when:2d&hl=ja&gl=JP&ceid=JP:ja",
    "https://news.google.com/rss/search?q=オンラインカジノ+アフィリエイト+when:2d&hl=ja&gl=JP&ceid=JP:ja",
]

YAHOO_SEARCH_URLS = [
    "https://news.yahoo.co.jp/search?p=オンラインカジノ",
    "https://news.yahoo.co.jp/search?p=オンカジ",
    "https://news.yahoo.co.jp/search?p=オンライン賭博",
    "https://news.yahoo.co.jp/search?p=カジノサイト",
    "https://news.yahoo.co.jp/search?p=海外カジノ",
    "https://news.yahoo.co.jp/search?p=オンラインカジノ%20逮捕",
    "https://news.yahoo.co.jp/search?p=オンラインカジノ%20規制",
    "https://news.yahoo.co.jp/search?p=オンラインカジノ%20摘発",
    "https://news.yahoo.co.jp/search?p=オンラインカジノ%20削除要請",
]

KEYWORDS = [
    "オンラインカジノ", "オンカジ", "オンライン賭博", "違法カジノ",
    "カジノサイト", "カジノアプリ", "海外カジノ",
    "賭博", "ギャンブル", "賭博罪",
    "逮捕", "摘発", "規制", "接続遮断", "削除要請",
    "決済", "送金", "入金", "出金",
    "暗号資産", "仮想通貨",
    "広告", "アフィリエイト", "宣伝"
]

CATEGORY_RULES = {
    "🚨 Аресты / расследования": ["逮捕", "摘発", "書類送検", "容疑", "警察", "賭博罪"],
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
        json.dump(list(sent)[-700:], f, ensure_ascii=False, indent=2)

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

def parse_date_raw(raw):
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

def parse_date(entry):
    raw = entry.get("published") or entry.get("updated")
    return parse_date_raw(raw)

def is_fresh(published_dt):
    if not published_dt:
        return True
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
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = clean_text(" ".join(paragraphs))

        if len(text) < 150:
            return ""

        return text[:3500]
    except Exception:
        return ""

def make_summary_ru(title_ru, article_ru):
    text = article_ru if article_ru and article_ru != "Не удалось перевести автоматически." else title_ru
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    summary = " ".join(sentences[:4]).strip()
    return summary[:1100] if summary else title_ru

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

def get_google_items():
    items = []

    for feed_url in GOOGLE_RSS_FEEDS:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries[:15]:
            title = clean_text(entry.get("title", ""))
            summary = clean_text(entry.get("summary", ""))
            link = entry.get("link", "").strip()
            published_dt, published_pretty = parse_date(entry)

            if not title or not link:
                continue

            items.append({
                "title": title,
                "summary": summary,
                "link": link,
                "published_dt": published_dt,
                "published_pretty": published_pretty,
                "source": "Google News",
            })

    return items

def get_yahoo_items():
    items = []

    headers = {"User-Agent": "Mozilla/5.0"}

    for url in YAHOO_SEARCH_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "lxml")

            links = soup.find_all("a", href=True)

            for a in links[:40]:
                href = a.get("href", "")
                title = clean_text(a.get_text(" ", strip=True))

                if not title or len(title) < 12:
                    continue

                if "news.yahoo.co.jp/articles/" not in href:
                    continue

                items.append({
                    "title": title,
                    "summary": "",
                    "link": href,
                    "published_dt": None,
                    "published_pretty": "Дата не указана / Yahoo",
                    "source": "Yahoo Japan",
                })

        except Exception:
            continue

    return items

def main():
    sent = load_sent()
    new_count = 0
    seen_links = set()

    items = get_google_items() + get_yahoo_items()

    for item in items:
        title = item["title"]
        summary = item["summary"]
        link = item["link"]
        published_dt = item["published_dt"]
        published_pretty = item["published_pretty"]
        source = item["source"]

        if link in seen_links:
            continue
        seen_links.add(link)

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
        article_ru = translate_to_ru(source_text) if source_text else ""
        short_summary = make_summary_ru(title_ru, article_ru)

        category = detect_category(f"{title} {summary} {article_jp}")

        message = f"""🇯🇵 JAPAN iGAMING NEWS

📅 {published_pretty}
🗞 Источник поиска: {source}

🏷 Категория:
{category}

📰 Оригинал:
{title}

🇷🇺 Заголовок:
{title_ru}

📌 Краткая выжимка:
{short_summary}

🔗 Ссылка:
{link}
"""

        send_telegram(message)
        sent.add(news_id)
        new_count += 1

        if new_count >= MAX_NEWS:
            break

    if new_count == 0:
        send_telegram("За последние 48 часов новых новостей по японскому online casino / iGaming не найдено.")

    save_sent(sent)

if __name__ == "__main__":
    main()
