#!/usr/bin/env python3
"""
VNL Finals 對戰同步。

決賽週期（8 強～冠軍賽）的對手要等前一輪打完才知道，data/vnl_{season}.yaml
沒辦法像小組賽那樣提前整理好。這支模組在賽事日期窗口內，直接讀 Wikipedia
該屆賽事頁面的 wikitext（不是渲染後的 HTML/markdown——那個常常沒同步更新），
解析「== Final round ==」段落裡的 {{Vb res 12|...}} 賽果模板，抓出「已確定對手」
且含追蹤隊伍的場次，補進 data/vnl_{season}.yaml，讓既有的 fetch_vnl() 自然讀到。

只在對應賽事的日期窗口內才會發出 HTTP 請求；抓取或解析失敗只記警告、
不拋例外中斷整體流程（generate.py 還要處理 NBA/MLB/F1 等其他賽事）。

每年的 Finals 對戰隊伍、場館都不一樣，FINALS_EVENTS 需要每年手動更新一次
（跟 data/vnl_{season}.yaml 本身一樣，是有意設計成手動維護的部分）。
"""
import re
import logging
from datetime import date

log = logging.getLogger("sports-cal")

# FIVB/IOC 三碼 → config.yaml 使用的英文隊名（要跟 config.yaml teams 清單裡的拼法對上）
TEAM_CODE_TO_NAME = {
    "JPN": "Japan",
    "BRA": "Brazil",
    "CHN": "China",
    "USA": "United States",
    "ITA": "Italy",
    "NED": "Netherlands",
    "TUR": "Turkey",
    "CAN": "Canada",
    "POL": "Poland",
    "SLO": "Slovenia",
    "UKR": "Ukraine",
}

MONTH_ABBR = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# 2026 VNL Finals：日期窗口內才會去抓 Wikipedia；隊伍代碼清單是賽前（小組賽戰績出爐後）
# 就已知的 8 強名單，用來防呆——wikitext 出現不在這份名單裡的代碼，視為異常直接跳過不採信。
FINALS_EVENTS = [
    {
        "gender": "women",
        "wiki_title": "2026_FIVB_Women's_Volleyball_Nations_League",
        "window": (date(2026, 7, 21), date(2026, 7, 26)),  # TEMP：TG 活體測試用，測完會 revert
        "tz": "Asia/Macau",
        "venue": "Macau East Asian Games Dome",
        "qualified": {"USA", "CHN", "ITA", "NED", "BRA", "JPN", "TUR", "CAN"},
    },
    {
        "gender": "men",
        "wiki_title": "2026_FIVB_Men's_Volleyball_Nations_League",
        "window": (date(2026, 7, 29), date(2026, 8, 2)),
        "tz": "Asia/Shanghai",
        "venue": "Beilun Gymnasium",
        "qualified": {"JPN", "CHN", "POL", "SLO", "ITA", "USA", "TUR", "UKR"},
    },
]

ROUND_HEADING_RE = re.compile(r"^=== (.+?) ===\s*$")
ROW_RE = re.compile(r"\{\{Vb res 12\|([^|]*)\|([^|]*)\|")
HOME_RE = re.compile(r"\{\{vbw?-rt\|([A-Z]{3})\}\}")
AWAY_RE = re.compile(r"\{\{vbw?\|([A-Z]{3})\}\}")
WIKI_DATE_RE = re.compile(r"^(\d{1,2}) (\w{3})$")


def _parse_wiki_date(raw, year):
    m = WIKI_DATE_RE.match(raw.strip())
    if not m:
        return None
    day, mon = m.groups()
    month = MONTH_ABBR.get(mon)
    if not month:
        return None
    return f"{year}-{month:02d}-{int(day):02d}"


def _fetch_final_round_wikitext(session, wiki_title):
    resp = session.get(
        "https://en.wikipedia.org/w/index.php",
        params={"title": wiki_title, "action": "raw"},
        timeout=20,
    )
    resp.raise_for_status()
    content = resp.text
    # 頁面裡 "Final round" 這個標題出現兩次（規則說明段落 + 真正賽果段落），
    # 用「剛好兩個等號」鎖定二級標題，避免匹配到三級標題（Venues 底下也有同名子標題）。
    start_m = re.search(r"(?<!=)== Final round ==(?!=)", content)
    if not start_m:
        raise ValueError("找不到 '== Final round ==' 段落，頁面結構可能變了")
    rest = content[start_m.end():]
    end_m = re.search(r"\n(?<!=)== [^=\n]+ ==(?!=)", rest)
    section = rest[: end_m.start()] if end_m else rest
    return section


def _parse_rows(wikitext):
    """回傳 [(round_name, date_raw, time_raw, home_code_or_None, away_code_or_None), ...]"""
    rows = []
    current_round = None
    for line in wikitext.splitlines():
        heading_m = ROUND_HEADING_RE.match(line.strip())
        if heading_m:
            current_round = heading_m.group(1)
            continue
        if "{{Vb res 12|" not in line:
            continue
        row_m = ROW_RE.search(line)
        if not row_m:
            continue
        date_raw, time_raw = row_m.group(1).strip(), row_m.group(2).strip()
        home_m = HOME_RE.search(line)
        away_m = AWAY_RE.search(line)
        home = home_m.group(1) if home_m else None
        away = away_m.group(1) if away_m else None
        rows.append((current_round, date_raw, time_raw, home, away))
    return rows


def _existing_match_keys(data_path):
    """讀現有 yaml，回傳已存在的 (date, home, away) 集合，用來去重。"""
    if not data_path.exists():
        return set()
    try:
        import yaml
        data = yaml.safe_load(data_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        log.warning("VNL Finals sync：讀取既有 %s 失敗，跳過去重比對：%s", data_path, e)
        return set()
    keys = set()
    for m in data.get("matches", []) or []:
        keys.add((str(m.get("date")), m.get("home"), m.get("away")))
    return keys


def sync_vnl_finals(cfg, session, data_path, today=None):
    """
    在 data_path（data/vnl_{season}.yaml）裡補上「已確定對手」且含追蹤隊伍的 Finals 場次。
    只在對應賽事的日期窗口內才動作；抓取/解析失敗只記警告、回傳 0，不中斷呼叫端流程。
    回傳實際新增的場次數量。
    """
    if not cfg.get("enabled"):
        return 0
    today = today or date.today()
    men_tracked = set(cfg.get("teams", {}).get("men", []) or [])
    women_tracked = set(cfg.get("teams", {}).get("women", []) or [])

    active_events = [e for e in FINALS_EVENTS if e["window"][0] <= today <= e["window"][1]]
    if not active_events:
        return 0

    import yaml

    existing_keys = _existing_match_keys(data_path)
    new_lines = []

    for event in active_events:
        tracked = men_tracked if event["gender"] == "men" else women_tracked
        if not tracked:
            continue
        try:
            wikitext = _fetch_final_round_wikitext(session, event["wiki_title"])
            rows = _parse_rows(wikitext)
        except Exception as e:
            log.warning("VNL Finals sync（%s）抓取/解析失敗，跳過本輪：%s", event["gender"], e)
            continue

        year = today.year
        for round_name, date_raw, time_raw, home_code, away_code in rows:
            if not home_code or not away_code or not time_raw:
                continue  # 對手還沒定，或時間還沒公布，先跳過等下次
            if home_code not in event["qualified"] or away_code not in event["qualified"]:
                log.warning(
                    "VNL Finals sync（%s）出現非預期隊伍代碼 %s/%s，跳過這筆（可能是編輯錯誤或頁面格式跑掉）",
                    event["gender"], home_code, away_code,
                )
                continue
            home_name = TEAM_CODE_TO_NAME.get(home_code)
            away_name = TEAM_CODE_TO_NAME.get(away_code)
            if not home_name or not away_name:
                continue
            if home_name not in tracked and away_name not in tracked:
                continue
            match_date = _parse_wiki_date(date_raw, year)
            if not match_date:
                log.warning("VNL Finals sync：日期格式看不懂 %r，跳過", date_raw)
                continue
            key = (match_date, home_name, away_name)
            if key in existing_keys:
                continue

            round_label = f"（VNL Finals {round_name}）" if round_name else "（VNL Finals）"
            # round_name / time_raw 來自 Wikipedia wikitext，可能含雙引號或反斜線等特殊字元；
            # 不手刻 YAML 字串，改用 yaml.safe_dump 序列化 dict，讓 PyYAML 正確轉義。
            record = {
                "date": match_date,
                "time": time_raw,
                "tz": event["tz"],
                "gender": event["gender"],
                "home": home_name,
                "away": away_name,
                "venue": f'{event["venue"]}{round_label}',
            }
            flow = yaml.safe_dump(
                record, default_flow_style=True, allow_unicode=True, sort_keys=False
            ).strip()
            new_lines.append(f"  - {flow}")
            existing_keys.add(key)
            log.info(
                "VNL Finals sync：新增 %s %s vs %s（%s %s）",
                round_name, home_name, away_name, match_date, time_raw,
            )

    if not new_lines:
        return 0

    with data_path.open("a", encoding="utf-8") as f:
        f.write("\n  # ---- VNL Finals 自動同步（vnl_finals_sync.py，來源：Wikipedia wikitext） ----\n")
        f.write("\n".join(new_lines) + "\n")

    return len(new_lines)
