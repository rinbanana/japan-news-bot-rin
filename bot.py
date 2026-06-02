import os
import json
import hashlib
import re
import html
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

SENT_FILE = "sent_news.json"
STATS_FILE = "news_stats.json"

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

JAPAN_CONTEXT = [
    "日本", "国内", "警察", "総務省", "政府", "日本人", "千葉", "東京", "大阪",
    "オンラインカジノ", "オンカジ", "日本向け"
]

BAD_TEXT_MARKERS = [
    "JavaScript",
    "javascript",
    "Cookie",
    "enable JavaScript",
    "JavaScriptを有効",
    "現在無効になっています",
    "Access Denied",
    "403 Forbidden"
]

CATEGORY_RULES = {
    "Аресты / расследования": ["逮捕", "摘発", "書類送検", "容疑", "警察", "賭博罪"],
    "Регулирование": ["規制", "違法", "接続遮断", "削除要請", "総務省", "政府"],
    "Платежи": ["決済", "送金", "銀行", "クレジット", "入金", "出金"],
    "Крипто": ["暗号資産", "仮想通貨", "ビットコイン", "crypto"],
    "Affiliate / Marketing": ["広告", "アフィリエイト", "宣伝", "SNS", "インフルエンサー"],
}

def load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_sent():
    return set(load_json_file(SENT_FILE, []))

def save_sent(sent):
    save_json_file(SENT_FILE, list(sent)[-700:])

def load_stats():
    return load_json_file(STATS_FILE, {})

def save_stats(stats):
    save_json_file(STATS_FILE, stats)

def make_id(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(" ", strip=True)

def remove_publisher_suffix(text):
    text = re.sub(r"\s+[-｜|]\s+[^-｜|]{1,50}$", "", text)
    text = re.sub(r"\s+\d{1,2}/\d{1,2}\([^)]+\)\s+\d{1,2}:\d{2}$", "", text)
    return text.strip()

def clean_text(text):
    text = clean_html(text)
    text = re.sub(r"\s+", " ", text)
    text = remove_publisher_suffix(text)
    return text.strip()

def translate_to_ru(text):
    if not text:
        return ""
    try:
        return GoogleTranslator(source="auto", target="ru").translate(text[:4500])
    except Exception:
        return ""

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
        return False
    return datetime.now(timezone.utc) - published_dt <= timedelta(hours=HOURS_LIMIT)

def contains_bad_text(text):
    return any(marker.lower() in text.lower() for marker in BAD_TEXT_MARKERS)

def is_relevant(title, summary, article_text=""):
    combined = f"{title} {summary} {article_text}".lower()
    has_keyword = any(k.lower() in combined for k in KEYWORDS)
    has_japan = any(k.lower() in combined for k in JAPAN_CONTEXT)
    return has_keyword and has_japan

def detect_category(text):
    for category, words in CATEGORY_RULES.items():
        if any(word.lower() in text.lower() for word in words):
            return category
    return "Online Casino / General"

def fetch_article_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = clean_text(" ".join(paragraphs))

        if contains_bad_text(text):
            return ""

        if len(text) < 250:
            return ""

        return text[:3500]
    except Exception:
        return ""

def make_summary_ru(title_ru, article_ru):
    if not article_ru:
        return "Полный текст статьи не удалось получить. Доступен только заголовок и ссылка на источник."

    text = re.sub(r"\s+", " ", article_ru).strip()

    if len(text) < 180:
        return "Полный текст статьи не удалось получить. Доступен только заголовок и ссылка на источник."

    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    summary = " ".join(sentences[:4]).strip()

    summary = re.sub(r"\s+[-–—]\s+[A-Za-zА-Яа-я0-9 ._/]{2,50}$", "", summary)
    return summary[:1100]

def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
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

            if not published_dt:
                continue

            items.append({
                "title": title,
                "summary": summary,
                "link": link,
                "published_dt": published_dt,
                "published_pretty": published_pretty,
            })

    return items

def build_market_note(category_counts):
    if not category_counts:
        return "Сигналов по рынку недостаточно."

    top_category = max(category_counts, key=category_counts.get)

    if top_category == "Регулирование":
        return "Главный фокус — регулирование. Для affiliate это сигнал внимательнее следить за формулировками рекламы, источниками трафика и страницами, ориентированными на Японию."
    if top_category == "Аресты / расследования":
        return "Главный фокус — расследования и правоприменение. Это повышает риск для серого промо и брендов, которые явно таргетируют японских игроков."
    if top_category == "Платежи":
        return "Главный фокус — платежи. Важно отслеживать методы депозитов и выводов, особенно если воронка связана с crypto, bank transfer или e-wallet."
    if top_category == "Крипто":
        return "Главный фокус — крипто. Стоит следить за связкой crypto payments + offshore casino, так как она может стать отдельной темой регулирования."
    if top_category == "Affiliate / Marketing":
        return "Главный фокус — реклама и продвижение. Для affiliate это особенно важно: могут появляться риски по SEO, SNS, influencer traffic и рекламным заявлениям."

    return "Общий фон по онлайн-казино в Японии остаётся чувствительным, но без одного доминирующего сигнала."

def compare_with_previous(current_stats, previous_stats):
    if not previous_stats:
        return "Сравнение с прошлым запуском: данных пока нет."

    prev_total = previous_stats.get("total", 0)
    cur_total = current_stats.get("total", 0)

    if cur_total > prev_total:
        direction = "новостей стало больше"
    elif cur_total < prev_total:
        direction = "новостей стало меньше"
    else:
        direction = "количество новостей примерно такое же"

    prev_categories = previous_stats.get("categories", {})
    cur_categories = current_stats.get("categories", {})

    growing = []
    for cat, count in cur_categories.items():
        if count > prev_categories.get(cat, 0):
            growing.append(cat)

    if growing:
        return f"Сравнение с прошлым запуском: {direction}. Выросли темы: {', '.join(growing)}."
    return f"Сравнение с прошлым запуском: {direction}. Явного роста по отдельным темам нет."

def send_digest(found_news, previous_stats):
    if not found_news:
        return

    category_counts = {}

    for item in found_news:
        category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1

    current_stats = {
        "total": len(found_news),
        "categories": category_counts,
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
    }

    categories_text = "\n".join(
        [f"{cat}: {count}" for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True)]
    )

    market_note = build_market_note(category_counts)
    comparison = compare_with_previous(current_stats, previous_stats)

    digest = f"""🇯🇵 <b>Итог по Japan iGaming за последние {HOURS_LIMIT} часов</b>

Всего новых новостей: {len(found_news)}

<b>Категории:</b>
{html.escape(categories_text)}

<b>Вывод для рынка:</b>
{html.escape(market_note)}

<b>Динамика:</b>
{html.escape(comparison)}
"""

    send_telegram(digest)
    save_stats(current_stats)

def main():
    sent = load_sent()
    previous_stats = load_stats()

    new_count = 0
    seen_links = set()
    found_news = []

    items = get_google_items()

    for item in items:
        title = item["title"]
        summary = item["summary"]
        link = item["link"]
        published_dt = item["published_dt"]
        published_pretty = item["published_pretty"]

        if link in seen_links:
            continue
        seen_links.add(link)

        if not is_fresh(published_dt):
            continue

        article_jp = fetch_article_text(link)
        source_text = article_jp if article_jp else ""

        if contains_bad_text(source_text):
            continue

        if not is_relevant(title, summary, article_jp):
            continue

        news_id = make_id(title + link)
        if news_id in sent:
            continue

        title_ru = translate_to_ru(title)
        article_ru = translate_to_ru(source_text) if source_text else ""
        short_summary = make_summary_ru(title_ru, article_ru)

        category = detect_category(f"{title} {summary} {article_jp}")

        message = f"""🇯🇵 <b>JAPAN iGAMING NEWS</b>

Дата: {html.escape(published_pretty)}
Категория: {html.escape(category)}

<b>Оригинал:</b>
{html.escape(title)}

<b>Заголовок:</b>
{html.escape(title_ru)}

<b>Краткая выжимка:</b>
{html.escape(short_summary)}

🔗 <a href="{html.escape(link, quote=True)}">Открыть источник</a>
"""

        send_telegram(message)

        sent.add(news_id)
        found_news.append({
            "title": title,
            "category": category,
            "link": link,
        })

        new_count += 1

        if new_count >= MAX_NEWS:
            break

    if new_count == 0:
        send_telegram("🇯🇵 За последние 48 часов новых новостей по японскому online casino / iGaming не найдено.")
    else:
        send_digest(found_news, previous_stats)

    save_sent(sent)

if __name__ == "__main__":
    main()
