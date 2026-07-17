#!/usr/bin/env python3
"""
HYROX 開賣監控
監控 HYROX Taipei 2027（3/12–14）與 HYROX Nagoya 2027（4/16–18）的官網頁面，
偵測「開放報名購票」的瞬間並透過 Telegram 通知（附可直接點的購票／場次連結按鈕）。

判斷邏輯（雙訊號，已用開賣中的 Chiba 場次頁對照驗證）：
- 未開賣：頁面含「Ticket sales start soon!」文字（不分大小寫）、且找不到購票連結
- 開賣中：上述文字消失、且抓到新的購票連結
  （日本站格式如 https://japan.hyrox.com/event/hyrox-xxx；
    已知的 race-for-impact-charity-tickets 慈善票連結不算購票訊號，需排除）

三種通知（狀態記錄在同目錄的 state.json，避免重複發送）：
1. 🔥 開賣：soon 文字消失 且 找到購票連結 → 只通知一次（state.notified_open）
2. ⏰ 異動：票務關鍵字內容 hash 變了，或 soon 文字消失但還沒找到連結
   → 同一個 hash 只通知一次，並把 hot_until 設為現在 +72 小時
     （熱區內每次喚醒都真的檢查，不受 30 分鐘節流限制）
3. ⚠️ 失靈：連續 3 次抓取失敗，或頁面結構完全認不得（soon 文字、購票連結兩者皆判斷不出）
   → 同一個失敗串只通知一次，之後每 24 小時提醒一次直到恢復

節流：workflow 排程每 5 分鐘喚醒一次，但本腳本平常自我節流成 30 分鐘才真的檢查一次；
若有任一監控目標處於「熱區」（now < hot_until）則不節流，每次喚醒都檢查。

Telegram：TOKEN / CHAT_ID 一律從環境變數 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 讀取，
沒有設定就把訊息印到 stdout 並標註「（未設 token，僅列印）」，絕不寫死在程式碼裡。
通知一律有聲（不設 disable_notification）。
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TAIPEI = ZoneInfo("Asia/Taipei")
ROOT = Path(__file__).parent
STATE_PATH = ROOT / "state.json"

THROTTLE_MINUTES = 30
HOT_WINDOW_HOURS = 72
FAILURE_ALERT_THRESHOLD = 3
FAILURE_REMIND_HOURS = 24

# 監控目標。台灣站的購票連結可能出現在事件頁或 /tickets/ 輔助頁，兩頁都抓。
TARGETS = [
    {
        # 【演習用，測完移除】千葉場已在開賣中，用來實彈驗證 🔥 開賣通知全流程
        "id": "hyrox_chiba_rehearsal",
        "name": "HYROX Chiba 2026（8/7–9）【演習】",
        "event_page": "https://hyroxjapan.com/event/hyrox-chiba/",
        "pages": [
            "https://hyroxjapan.com/event/hyrox-chiba/",
        ],
        "own_domains": ["hyroxjapan.com"],
    },
    {
        "id": "hyrox_taipei_2027",
        "name": "HYROX Taipei 2027（3/12–14）",
        "event_page": "https://hyroxtaiwan.com/event/hyrox-taipei/",
        "pages": [
            "https://hyroxtaiwan.com/event/hyrox-taipei/",
        ],
        "own_domains": ["hyroxtaiwan.com"],
    },
    {
        "id": "hyrox_nagoya_2027",
        "name": "HYROX Nagoya 2027（4/16–18）",
        "event_page": "https://hyroxjapan.com/event/hyrox-nagoya/",
        "pages": [
            "https://hyroxjapan.com/event/hyrox-nagoya/",
        ],
        "own_domains": ["hyroxjapan.com"],
    },
]

# 實測發現這兩個站會擋預設 bot UA（回 403），帶 Chrome UA 就能穩定拿到 200。
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": CHROME_UA,
    "Accept-Language": "en-US,en;q=0.9",
})

# 已知的慈善票連結，開賣前後都存在，不算開賣訊號
CHARITY_TICKET_PATTERN = re.compile(r"race-for-impact-charity-tickets", re.I)
# 購票連結訊號 1：官網子網域 xxx.hyrox.com/event/...（實測日本站確認的格式）
TICKET_SUBDOMAIN_PATTERN = re.compile(r'href="(https?://[a-z0-9-]+\.hyrox\.com/event/[^"]+)"', re.I)
# 購票連結訊號 2（備援）：含 ticket 關鍵字，但排除自家網域與慈善票連結
GENERIC_TICKET_HREF_PATTERN = re.compile(r'href="(https?://[^"]*ticket[^"]*)"', re.I)

SOON_TEXT_PATTERN = re.compile(r"sales\s+start\s+soon", re.I)
# 判斷頁面結構還認不認得的基本標記，避免把擋牆頁／驗證頁誤判成「未開賣」
BASELINE_MARKER_PATTERN = re.compile(r"hyrox", re.I)
BLOCK_PAGE_PATTERN = re.compile(r"(just a moment|attention required|access denied|cf-error)", re.I)

TICKET_KEYWORD_LINE_PATTERN = re.compile(r"(ticket|sale|register|entry|20\d{2})", re.I)
SCRIPT_STYLE_PATTERN = re.compile(r"<script.*?</script>|<style.*?</style>", re.I | re.S)
TAG_PATTERN = re.compile(r"<[^>]+>")


def now_taipei() -> datetime:
    return datetime.now(TAIPEI)


def fmt_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ---------------- state ----------------

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_target_state() -> dict:
    return {
        "notified_open": False,
        "last_ticket_hash": None,
        "notified_hash": None,
        "hot_until": None,
        "fail_streak": 0,
        "fail_notified": False,
        "last_fail_notified_at": None,
    }


# ---------------- fetch & parse ----------------

def fetch_page(url: str, timeout: int = 20):
    """回傳 (成功?, html 或 None, 說明字串)"""
    try:
        resp = SESSION.get(url, timeout=timeout)
    except requests.RequestException as e:
        return False, None, f"連線失敗: {e}"
    if resp.status_code != 200:
        return False, None, f"HTTP {resp.status_code}"
    return True, resp.text, "OK"


def is_page_recognizable(html: str) -> bool:
    """基本結構檢查：太短、疑似擋牆/驗證頁、或沒有 hyrox 字樣，都算認不得"""
    if not html or len(html) < 5000:
        return False
    if BLOCK_PAGE_PATTERN.search(html):
        return False
    if not BASELINE_MARKER_PATTERN.search(html):
        return False
    return True


def has_soon_text(html: str) -> bool:
    return bool(SOON_TEXT_PATTERN.search(html))


def find_ticket_links(html: str, own_domains) -> list:
    links = []
    for m in TICKET_SUBDOMAIN_PATTERN.finditer(html):
        url = m.group(1)
        if CHARITY_TICKET_PATTERN.search(url):
            continue
        if url not in links:
            links.append(url)
    for m in GENERIC_TICKET_HREF_PATTERN.finditer(html):
        url = m.group(1)
        if CHARITY_TICKET_PATTERN.search(url):
            continue
        if any(d in url for d in own_domains):
            continue
        if url not in links:
            links.append(url)
    return links


def ticket_keyword_hash(html: str):
    """去除 tag/script 後、只保留含票務關鍵字的行做 hash，減少無關改版誤報"""
    no_script = SCRIPT_STYLE_PATTERN.sub(" ", html)
    text = TAG_PATTERN.sub("\n", no_script)
    lines = [ln.strip() for ln in text.splitlines()]
    keyword_lines = [ln for ln in lines if ln and TICKET_KEYWORD_LINE_PATTERN.search(ln)]
    joined = "\n".join(keyword_lines)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), keyword_lines


def classify_html(html: str, own_domains) -> dict:
    recognizable = is_page_recognizable(html)
    soon = has_soon_text(html) if recognizable else False
    links = find_ticket_links(html, own_domains) if recognizable else []
    return {"recognizable": recognizable, "soon": soon, "links": links}


def is_open(html: str, own_domains=()) -> bool:
    """開賣中判斷：soon 文字消失 且 找到購票連結（供 --selftest 使用）"""
    info = classify_html(html, own_domains)
    return info["recognizable"] and not info["soon"] and bool(info["links"])


# ---------------- Telegram 發送 ----------------

def build_markup(buttons) -> dict:
    return {"inline_keyboard": [[{"text": label, "url": url} for label, url in buttons]]}


def deliver(text: str, buttons, dry_run: bool) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    markup = build_markup(buttons) if buttons else None

    if dry_run:
        print("---- 訊息預覽（--dry-run，不會實際發送）----")
        print(text)
        if markup:
            print("按鈕:", json.dumps(markup, ensure_ascii=False))
        print("--------------------------------------------")
        return

    if not token or not chat_id:
        print("（未設 token，僅列印）")
        print(text)
        if markup:
            print("按鈕:", json.dumps(markup, ensure_ascii=False))
        return

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_notification": False,  # 通知一律有聲
    }
    if markup:
        payload["reply_markup"] = json.dumps(markup, ensure_ascii=False)
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, timeout=20)
        if r.status_code != 200:
            print(f"Telegram 發送失敗：HTTP {r.status_code} {r.text}", file=sys.stderr)
    except requests.RequestException as e:
        print(f"Telegram 發送失敗：{e}", file=sys.stderr)


# ---------------- 三種通知 ----------------

def handle_open(target: dict, st: dict, now: datetime, dry_run: bool, links: list) -> None:
    st["notified_open"] = True
    link = links[0]
    text = (
        f"🔥 開賣了！{target['name']}\n"
        f"時間：{fmt_time(now)}（台北時間）\n"
        f"偵測到購票連結，手刀衝了！"
    )
    buttons = [("🎫 立刻購票", link), ("📄 場次頁面", target["event_page"])]
    deliver(text, buttons, dry_run)


def handle_change(target: dict, now: datetime, dry_run: bool, keyword_lines: list) -> None:
    snippet = "\n".join(keyword_lines)[:200]
    text = (
        f"⏰ 頁面異動：{target['name']}\n"
        f"時間：{fmt_time(now)}（台北時間）\n"
        f"變化片段：\n{snippet}\n"
        f"（接下來 72 小時會加快檢查頻率）"
    )
    buttons = [("📄 場次頁面", target["event_page"])]
    deliver(text, buttons, dry_run)


def handle_failure(target: dict, st: dict, now: datetime, dry_run: bool, fail_reasons: list) -> None:
    if st["fail_streak"] < FAILURE_ALERT_THRESHOLD:
        return
    should_notify = False
    if not st.get("fail_notified"):
        should_notify = True
    else:
        last = st.get("last_fail_notified_at")
        if last and (now - datetime.fromisoformat(last)) >= timedelta(hours=FAILURE_REMIND_HOURS):
            should_notify = True
    if not should_notify:
        return
    reasons_text = "\n".join(fail_reasons) if fail_reasons else "頁面結構認不得（soon 文字與購票連結皆判斷不出）"
    text = (
        f"⚠️ 監控異常：{target['name']}\n"
        f"時間：{fmt_time(now)}（台北時間）\n"
        f"連續 {st['fail_streak']} 次抓取失敗或結構異常：\n{reasons_text}"
    )
    buttons = [("📄 場次頁面", target["event_page"])]
    deliver(text, buttons, dry_run)
    st["fail_notified"] = True
    st["last_fail_notified_at"] = now.isoformat()


# ---------------- 主檢查流程 ----------------

def process_target(target: dict, state: dict, now: datetime, dry_run: bool) -> None:
    tid = target["id"]
    st = state.setdefault(tid, default_target_state())

    if st.get("notified_open"):
        print(f"[{target['name']}] 已通知開賣，略過檢查。")
        return

    htmls = []
    fail_reasons = []
    for url in target["pages"]:
        ok, html, reason = fetch_page(url)
        if ok:
            htmls.append(html)
        else:
            fail_reasons.append(f"{url} -> {reason}")

    recognizable = any(is_page_recognizable(h) for h in htmls) if htmls else False

    if not htmls or not recognizable:
        st["fail_streak"] = st.get("fail_streak", 0) + 1
        handle_failure(target, st, now, dry_run, fail_reasons)
        print(f"[{target['name']}] 抓取失敗或結構認不得（連續 {st['fail_streak']} 次）。")
        return

    if st["fail_streak"] > 0 or st.get("fail_notified"):
        print(f"[{target['name']}] 已恢復正常。")
    st["fail_streak"] = 0
    st["fail_notified"] = False
    st["last_fail_notified_at"] = None

    # soon 只要任一頁還看得到，就保守判定「還沒開賣」，避免用到快取頁誤判開賣
    soon = any(has_soon_text(h) for h in htmls)
    links = []
    for h in htmls:
        for link in find_ticket_links(h, target["own_domains"]):
            if link not in links:
                links.append(link)

    combined = "\n".join(htmls)
    new_hash, keyword_lines = ticket_keyword_hash(combined)
    old_hash = st.get("last_ticket_hash")
    st["last_ticket_hash"] = new_hash

    if not soon and links:
        handle_open(target, st, now, dry_run, links)
        print(f"[{target['name']}] 🔥 判定開賣！連結：{links[0]}")
        return

    hash_changed = old_hash is not None and new_hash != old_hash
    soon_gone_no_link = (not soon) and (not links)

    if hash_changed or soon_gone_no_link:
        if st.get("notified_hash") != new_hash:
            handle_change(target, now, dry_run, keyword_lines)
            st["notified_hash"] = new_hash
            st["hot_until"] = (now + timedelta(hours=HOT_WINDOW_HOURS)).isoformat()
            print(f"[{target['name']}] ⏰ 偵測到異動，已通知，進入 72 小時熱區。")
        else:
            print(f"[{target['name']}] 偵測到異動但這個版本已通知過，略過。")
        return

    print(f"[{target['name']}] 未開賣，狀態正常（soon={soon}, links={len(links)}）。")


def run_normal(dry_run: bool) -> None:
    state = load_state()
    meta = state.setdefault("_meta", {})
    now = now_taipei()

    hot = False
    for target in TARGETS:
        st = state.get(target["id"], {})
        hot_until = st.get("hot_until")
        if hot_until and now < datetime.fromisoformat(hot_until):
            hot = True

    last_check_str = meta.get("last_check")
    if last_check_str and not hot:
        last_check = datetime.fromisoformat(last_check_str)
        elapsed = now - last_check
        if elapsed < timedelta(minutes=THROTTLE_MINUTES):
            minutes = elapsed.total_seconds() / 60
            print(f"⏸ 節流中：距上次檢查 {minutes:.1f} 分鐘（未滿 {THROTTLE_MINUTES} 分鐘），本次跳過。")
            return

    print(f"開始檢查（{fmt_time(now)} 台北時間）{'[dry-run]' if dry_run else ''}")
    for target in TARGETS:
        process_target(target, state, now, dry_run)

    meta["last_check"] = now.isoformat()
    save_state(state)


# ---------------- --test / --selftest ----------------

def run_test(dry_run: bool) -> None:
    print("=== 測試模式：發送 3 則樣本訊息（不動用真實 state） ===")
    now = now_taipei()
    target = TARGETS[0]
    dummy_link = "https://taiwan.hyrox.com/event/hyrox-taipei-sample-xyz"

    print("\n--- 樣本 1/3：🔥 開賣通知 ---")
    text = (
        f"🔥 開賣了！{target['name']}\n"
        f"時間：{fmt_time(now)}（台北時間）\n"
        f"偵測到購票連結，手刀衝了！"
    )
    deliver(text, [("🎫 立刻購票", dummy_link), ("📄 場次頁面", target["event_page"])], dry_run)

    print("\n--- 樣本 2/3：⏰ 異動通知 ---")
    snippet = "Ticket sale registration entry opens 2027-01-15 for HYROX Taipei"[:200]
    text = (
        f"⏰ 頁面異動：{target['name']}\n"
        f"時間：{fmt_time(now)}（台北時間）\n"
        f"變化片段：\n{snippet}\n"
        f"（接下來 72 小時會加快檢查頻率）"
    )
    deliver(text, [("📄 場次頁面", target["event_page"])], dry_run)

    print("\n--- 樣本 3/3：⚠️ 失靈通知 ---")
    text = (
        f"⚠️ 監控異常：{target['name']}\n"
        f"時間：{fmt_time(now)}（台北時間）\n"
        f"連續 3 次抓取失敗或結構異常：\n{target['event_page']} -> HTTP 500（樣本，非真實錯誤）"
    )
    deliver(text, [("📄 場次頁面", target["event_page"])], dry_run)


def run_selftest() -> None:
    print("=== Selftest：開賣判斷函式驗證（實際打官網） ===")
    ok_all = True
    cases = [
        ("https://hyroxjapan.com/event/hyrox-chiba/", True, "Chiba（已知：開賣中）"),
        ("https://hyroxjapan.com/event/hyrox-nagoya/", False, "Nagoya（已知：未開賣）"),
    ]
    for url, expected_open, label in cases:
        ok, html, reason = fetch_page(url)
        if not ok:
            print(f"[FAIL] {label} 抓取失敗：{reason}")
            ok_all = False
            continue
        actual = is_open(html, own_domains=["hyroxjapan.com"])
        status = "PASS" if actual == expected_open else "FAIL"
        if status == "FAIL":
            ok_all = False
        expected_label = "開賣中" if expected_open else "未開賣"
        actual_label = "開賣中" if actual else "未開賣"
        print(f"[{status}] {label}: 預期「{expected_label}」，實際「{actual_label}」")

    sys.exit(0 if ok_all else 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="HYROX 開賣監控")
    parser.add_argument("--dry-run", action="store_true", help="正常檢查但訊息只印不發")
    parser.add_argument("--test", action="store_true", help="發送 3 則假樣本訊息（開賣/異動/失靈各一）")
    parser.add_argument("--selftest", action="store_true", help="用已知開賣中/未開賣的頁面驗證判斷函式")
    args = parser.parse_args()

    if args.selftest:
        run_selftest()
        return
    if args.test:
        run_test(args.dry_run)
        return
    run_normal(args.dry_run)


if __name__ == "__main__":
    main()
