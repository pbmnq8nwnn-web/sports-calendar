#!/usr/bin/env python3
"""
Sports Calendar Generator
抓取 NBA / MLB / F1 / 世界杯賽程，依 config.yaml 過濾指定球隊，
輸出 docs/sports.ics 供 Apple 行事曆訂閱。
"""
import os
import sys
import uuid
import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from pathlib import Path

import yaml
import requests
from icalendar import Calendar, Event

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("sports-cal")

UTC = ZoneInfo("UTC")
TAIPEI = ZoneInfo("Asia/Taipei")
ROOT = Path(__file__).parent
OUT_PATH = ROOT / "docs" / "sports.ics"
DIFF_SUMMARY_CHAR_LIMIT = 3500
DIFF_SUMMARY_SUFFIX_RESERVE = 80  # 保留給結尾「...還有 N 場」提示句的預算，避免加總後超過上限

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (sports-calendar-bot; https://github.com/your/repo)"
})


# ---------------- Helpers ----------------

def make_uid(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode()).hexdigest()
    return f"{h}@sports-calendar"


def make_event(uid, start_utc, duration_min, summary, location="", description=""):
    ev = Event()
    ev.add("uid", uid)
    # DTSTAMP 固定用比賽開始時間（而非 datetime.now()），讓輸出成為賽事資料的
    # 純函數：同樣資料永遠產生同樣的 .ics 內容，避免每次執行都被判定「有變更」。
    ev.add("dtstamp", start_utc)
    ev.add("dtstart", start_utc)
    ev.add("dtend", start_utc + timedelta(minutes=duration_min))
    ev.add("summary", summary)
    if location:
        ev.add("location", location)
    if description:
        ev.add("description", description)
    return ev


def fetch_json(url, params=None, timeout=30):
    log.info("GET %s %s", url, params or "")
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---------------- MLB ----------------

# MLB 全隊中文對照
MLB_ZH = {
    108: "天使", 109: "響尾蛇", 110: "金鶯", 111: "紅襪", 112: "小熊",
    113: "紅人", 114: "守護者", 115: "落磯", 116: "老虎", 117: "太空人",
    118: "皇家", 119: "道奇", 120: "國民", 121: "大都會", 133: "運動家",
    134: "海盜", 135: "教士", 136: "水手", 137: "巨人", 138: "紅雀",
    139: "光芒", 140: "遊騎兵", 141: "藍鳥", 142: "雙城", 143: "費城人",
    144: "勇士", 145: "白襪", 146: "馬林魚", 147: "洋基", 158: "釀酒人",
}


def fetch_mlb(cfg, season_year):
    if not cfg.get("enabled"):
        return []
    events = []
    team_ids = [t["id"] for t in cfg["teams"]]
    # 合併使用者選擇的中文名 + 全隊備用中文名
    zh_map = dict(MLB_ZH)
    zh_map.update({t["id"]: t["zh"] for t in cfg["teams"]})

    # 追蹤的球員
    tracked = cfg.get("tracked_players", []) or []
    tracked_pitcher_ids = {p["id"] for p in tracked if p.get("track") in ("pitcher", "both")}
    tracked_lineup_ids = {p["id"] for p in tracked if p.get("track") in ("lineup", "both")}
    tracked_zh = {p["id"]: p["zh"] for p in tracked}

    # MLB regular season roughly Mar-Oct; fetch broad range
    start = f"{season_year}-03-01"
    end = f"{season_year}-11-15"

    skipped = 0
    for tid in team_ids:
        try:
            params = {
                "sportId": 1,
                "teamId": tid,
                "startDate": start,
                "endDate": end,
            }
            # 只在有追蹤球員時 hydrate，省 payload
            if tracked_pitcher_ids or tracked_lineup_ids:
                hydrates = []
                if tracked_pitcher_ids:
                    hydrates.append("probablePitcher")
                if tracked_lineup_ids:
                    hydrates.append("lineups")
                params["hydrate"] = ",".join(hydrates)

            data = fetch_json(
                "https://statsapi.mlb.com/api/v1/schedule",
                params=params,
            )
        except Exception as e:
            log.error("MLB fetch failed for team %s: %s", tid, e)
            continue

        for d in data.get("dates", []):
            for g in d.get("games", []):
                home = g["teams"]["home"]["team"]
                away = g["teams"]["away"]["team"]
                # avoid duplicate when both teams in our list
                game_pk = g["gamePk"]
                start_utc = datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00"))
                # zh names
                zh_home = zh_map.get(home["id"], home["name"])
                zh_away = zh_map.get(away["id"], away["name"])
                summary = f"⚾ MLB｜{zh_away} @ {zh_home}"
                if g.get("seriesDescription") and g["seriesDescription"] != "Regular Season":
                    summary += f"（{g['seriesDescription']}）"

                # 比對追蹤球員 (保留次序：投手 → 野手；away → home)
                matched = []
                for side in ("away", "home"):
                    pp = g["teams"][side].get("probablePitcher") or {}
                    pid = pp.get("id")
                    if pid in tracked_pitcher_ids:
                        zh = tracked_zh.get(pid, pp.get("fullName", "?"))
                        if zh not in matched:
                            matched.append(zh)

                # 野手陣容：lineups.homePlayers / awayPlayers（list of player objs）
                lineups = g.get("lineups") or {}
                for key in ("awayPlayers", "homePlayers"):
                    for p in lineups.get(key, []) or []:
                        pid = p.get("id")
                        if pid in tracked_lineup_ids:
                            zh = tracked_zh.get(pid, p.get("fullName", "?"))
                            if zh not in matched:
                                matched.append(zh)

                # 只有追蹤球員有出賽（先發投手命中，或打線已公布且命中）才收進行事曆
                if not matched:
                    skipped += 1
                    continue

                summary += "  🎯" + "、".join(matched)

                venue = g.get("venue", {}).get("name", "")
                uid = make_uid("mlb", game_pk)
                events.append(make_event(
                    uid, start_utc, 210,  # ~3.5h
                    summary,
                    location=venue,
                    description=f"{away['name']} @ {home['name']}",
                ))

    # dedupe by uid
    seen = set()
    uniq = []
    for ev in events:
        u = str(ev["uid"])
        if u not in seen:
            seen.add(u)
            uniq.append(ev)
    log.info("MLB: %d events (%d games skipped, no tracked player matched)", len(uniq), skipped)
    return uniq


# ---------------- NBA ----------------

# NBA 全隊中文對照（ESPN id → 中文）
NBA_ZH = {
    1: "老鷹", 2: "塞爾提克", 17: "籃網", 30: "黃蜂", 4: "公牛",
    5: "騎士", 6: "獨行俠", 7: "金塊", 8: "活塞", 9: "勇士",
    10: "火箭", 11: "溜馬", 12: "快艇", 13: "湖人", 29: "灰熊",
    14: "熱火", 15: "公鹿", 16: "灰狼", 3: "鵜鶘", 18: "尼克",
    25: "雷霆", 19: "魔術", 20: "76人", 21: "太陽", 22: "拓荒者",
    23: "國王", 24: "馬刺", 28: "暴龍", 26: "爵士", 27: "巫師",
}


def fetch_nba(cfg):
    if not cfg.get("enabled"):
        return []
    events = []
    # 合併使用者選擇的中文名 + 全隊備用中文名
    zh_map = dict(NBA_ZH)
    zh_map.update({t["id"]: t["zh"] for t in cfg["teams"]})

    # 跨季 + 跨 seasontype 抓取（seasontype: 1=Preseason, 2=Regular, 3=Postseason）
    # 6 月時 current season 已結束，next season 10 月開打，所以都抓
    today = date.today()
    seasons = [today.year, today.year + 1] if today.month >= 7 else [today.year - 1, today.year]
    seasontypes = [2, 3]  # 例行賽 + 季後賽（預設不抓季前賽，避免雜訊）

    # 25-26 賽季（ESPN season=2026）Leo 只想留季後賽（含附加賽 Play-In）紀錄，
    # 不留例行賽；26-27 賽季（season=2027）起維持抓全部賽程。
    # season=2026 之後會自然滑出兩季視窗（見上方 seasons 計算），不用手動清掉這行。
    NBA_POSTSEASON_ONLY_SEASON = 2026

    for team in cfg["teams"]:
        tid = team["id"]
        for season in seasons:
            stypes = [3] if season == NBA_POSTSEASON_ONLY_SEASON else seasontypes
            for stype in stypes:
                url = f"https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{tid}/schedule"
                try:
                    data = fetch_json(url, params={"season": season, "seasontype": stype})
                except Exception as e:
                    log.warning("NBA fetch failed team=%s season=%s type=%s: %s", tid, season, stype, e)
                    continue

                for ev in data.get("events", []):
                    comp = ev.get("competitions", [{}])[0]
                    start_iso = comp.get("date") or ev.get("date")
                    if not start_iso:
                        continue
                    try:
                        start_utc = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                    except Exception:
                        continue

                    competitors = comp.get("competitors", [])
                    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
                    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
                    home_team = home.get("team", {})
                    away_team = away.get("team", {})

                    try:
                        home_id = int(home_team.get("id", 0))
                        away_id = int(away_team.get("id", 0))
                    except (TypeError, ValueError):
                        continue

                    zh_home = zh_map.get(home_id, home_team.get("displayName", "?"))
                    zh_away = zh_map.get(away_id, away_team.get("displayName", "?"))

                    # 場次類型 label（從 API 回傳的 seasonType 推斷，比參數可靠）
                    type_name = ev.get("seasonType", {}).get("name", "") or ""
                    label = ""
                    if "Playoff" in type_name or "Postseason" in type_name or stype == 3:
                        # 嘗試從 notes 拿輪次資訊
                        notes = comp.get("notes", []) or []
                        round_text = ""
                        for n in notes:
                            head = n.get("headline", "") or ""
                            if any(k in head for k in ["Round", "Conference", "Finals"]):
                                round_text = head
                                break
                        label = f"（季後賽{' - ' + round_text if round_text else ''}）"
                    elif "Preseason" in type_name:
                        label = "（季前賽）"

                    summary = f"🏀 NBA｜{zh_away} @ {zh_home}{label}"
                    venue = comp.get("venue", {}).get("fullName", "")
                    event_id = ev.get("id") or comp.get("id")
                    uid = make_uid("nba", event_id)
                    events.append(make_event(
                        uid, start_utc, 150,  # ~2.5h
                        summary,
                        location=venue,
                        description=f"{away_team.get('displayName','')} @ {home_team.get('displayName','')}",
                    ))

    # dedupe by uid
    seen = set()
    uniq = []
    for ev in events:
        u = str(ev["uid"])
        if u not in seen:
            seen.add(u)
            uniq.append(ev)
    log.info("NBA: %d events", len(uniq))
    return uniq


# ---------------- F1 ----------------

F1_SESSION_NAMES = {
    "FirstPractice":     ("FP1", "練習一", 90, False),
    "SecondPractice":    ("FP2", "練習二", 90, False),
    "ThirdPractice":     ("FP3", "練習三", 90, False),
    "Qualifying":        ("Q",   "排位賽", 70, True),
    "SprintQualifying":  ("SQ",  "Sprint排位", 45, True),
    "Sprint":            ("S",   "Sprint正賽", 60, True),
    # the race itself is at race["date"]/["time"], handled separately
}


def f1_session_enabled(cfg, key):
    s = cfg.get("sessions", {})
    mapping = {
        "FirstPractice": "practice1",
        "SecondPractice": "practice2",
        "ThirdPractice": "practice3",
        "Qualifying": "qualifying",
        "SprintQualifying": "sprint_qualifying",
        "Sprint": "sprint",
    }
    return bool(s.get(mapping.get(key, ""), False))


def fetch_f1(cfg):
    if not cfg.get("enabled"):
        return []
    events = []
    season = cfg.get("season", date.today().year)
    try:
        data = fetch_json(f"https://api.jolpi.ca/ergast/f1/{season}.json")
    except Exception as e:
        log.error("F1 fetch failed: %s", e)
        return []

    race_session_enabled = cfg.get("sessions", {}).get("race", True)

    for race in data["MRData"]["RaceTable"]["Races"]:
        round_no = race["round"]
        name = race["raceName"]
        circuit = race["Circuit"]["circuitName"]
        loc = race["Circuit"]["Location"]
        location = f"{loc['locality']}, {loc['country']}"

        # Race itself
        if race_session_enabled:
            try:
                start_utc = datetime.fromisoformat(
                    f"{race['date']}T{race.get('time', '00:00:00Z').replace('Z','+00:00')}"
                )
                uid = make_uid("f1", season, round_no, "Race")
                events.append(make_event(
                    uid, start_utc, 120,
                    f"🏎️ F1｜R{round_no} {name}（正賽）",
                    location=f"{circuit}, {location}",
                    description=f"Round {round_no} - {name}",
                ))
            except Exception as e:
                log.warning("F1 race time parse failed for round %s: %s", round_no, e)

        # Other sessions
        for key, (short, zh, dur, _) in F1_SESSION_NAMES.items():
            if key not in race:
                continue
            if not f1_session_enabled(cfg, key):
                continue
            sess = race[key]
            try:
                start_utc = datetime.fromisoformat(
                    f"{sess['date']}T{sess['time'].replace('Z','+00:00')}"
                )
                uid = make_uid("f1", season, round_no, key)
                events.append(make_event(
                    uid, start_utc, dur,
                    f"🏎️ F1｜R{round_no} {name}（{zh}）",
                    location=f"{circuit}, {location}",
                    description=f"Round {round_no} - {name} - {short}",
                ))
            except Exception as e:
                log.warning("F1 %s parse failed for round %s: %s", key, round_no, e)

    log.info("F1: %d events", len(events))
    return events


# ---------------- World Cup ----------------

# 國名中文對照（涵蓋 2026 世界杯全 48 隊 + 常見會出現的隊伍）
WC_ZH = {
    "Argentina": "阿根廷", "Brazil": "巴西", "France": "法國",
    "England": "英格蘭", "Japan": "日本", "South Korea": "韓國",
    "Norway": "挪威", "Portugal": "葡萄牙", "Spain": "西班牙",
    "Mexico": "墨西哥", "USA": "美國", "Canada": "加拿大",
    "Germany": "德國", "Italy": "義大利", "Netherlands": "荷蘭",
    "Belgium": "比利時", "Croatia": "克羅埃西亞", "Uruguay": "烏拉圭",
    "Colombia": "哥倫比亞", "Morocco": "摩洛哥", "Senegal": "塞內加爾",
    "Australia": "澳洲", "Switzerland": "瑞士", "Denmark": "丹麥",
    "Poland": "波蘭", "Czechia": "捷克", "Serbia": "塞爾維亞",
    "Ecuador": "厄瓜多", "Iran": "伊朗", "Saudi Arabia": "沙烏地阿拉伯",
    "Qatar": "卡達", "Tunisia": "突尼西亞", "Cameroon": "喀麥隆",
    "Ghana": "迦納", "Costa Rica": "哥斯大黎加", "Wales": "威爾斯",
    "South Africa": "南非",
    # 補充
    "Sweden": "瑞典", "Norway": "挪威", "Finland": "芬蘭",
    "Austria": "奧地利", "Scotland": "蘇格蘭", "Ireland": "愛爾蘭",
    "Republic of Ireland": "愛爾蘭", "Wales": "威爾斯",
    "Iceland": "冰島", "Turkey": "土耳其", "Türkiye": "土耳其",
    "Greece": "希臘", "Romania": "羅馬尼亞", "Hungary": "匈牙利",
    "Ukraine": "烏克蘭", "Bosnia-Herzegovina": "波士尼亞與赫塞哥維納",
    "Slovakia": "斯洛伐克", "Slovenia": "斯洛維尼亞",
    "Albania": "阿爾巴尼亞", "North Macedonia": "北馬其頓",
    "Israel": "以色列",
    "Algeria": "阿爾及利亞", "Egypt": "埃及", "Nigeria": "奈及利亞",
    "Ivory Coast": "象牙海岸", "Côte d'Ivoire": "象牙海岸",
    "Mali": "馬利", "Burkina Faso": "布吉納法索",
    "Congo DR": "剛果民主共和國", "DR Congo": "剛果民主共和國",
    "Cape Verde": "維德角",
    "Iraq": "伊拉克", "Jordan": "約旦", "United Arab Emirates": "阿聯",
    "UAE": "阿聯", "Oman": "阿曼", "Uzbekistan": "烏茲別克",
    "Australia": "澳洲", "New Zealand": "紐西蘭",
    "Bolivia": "玻利維亞", "Paraguay": "巴拉圭", "Peru": "秘魯",
    "Venezuela": "委內瑞拉", "Chile": "智利",
    "Panama": "巴拿馬", "Honduras": "宏都拉斯", "El Salvador": "薩爾瓦多",
    "Guatemala": "瓜地馬拉", "Jamaica": "牙買加",
    "Trinidad and Tobago": "千里達及托巴哥",
    "Haiti": "海地", "Curaçao": "古拉索", "Suriname": "蘇利南",
}


_WC_PLACEHOLDER_RE = __import__("re").compile(r"Group ([A-L]) (1st|2nd|3rd|4th) Place")
_WC_ORD = {"1st": "1", "2nd": "2", "3rd": "3", "4th": "4"}


def _wc_zh(name):
    if name in WC_ZH:
        return WC_ZH[name]
    # 淘汰賽占位名翻譯：Group A 2nd Place → A 組第 2
    m = _WC_PLACEHOLDER_RE.match(name)
    if m:
        grp, ord_str = m.group(1), m.group(2)
        return f"{grp} 組第 {_WC_ORD.get(ord_str, ord_str)}"
    # 其他常見占位：Winner Match 49 / 32 Best 3rd 之類
    if "Winner Match" in name or "Match Winner" in name:
        return name.replace("Winner Match", "M").replace("Match Winner", "M")  # 縮短
    if "Best 3rd" in name:
        return name.replace("Best 3rd", "B3")
    return name


def fetch_worldcup(cfg):
    if not cfg.get("enabled"):
        return []
    events = []
    selected = set(cfg.get("teams", []))
    knockout_all = cfg.get("knockout_all", False)

    # World Cup 2026: 11 Jun – 19 Jul
    start = date(2026, 6, 11)
    end = date(2026, 7, 19)
    cur = start
    seen_event_ids = set()

    knockout_types = {"Round of 32", "Round of 16", "Quarterfinal",
                      "Semifinal", "3rd Place", "Final"}

    while cur <= end:
        date_str = cur.strftime("%Y%m%d")
        try:
            data = fetch_json(
                "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
                params={"dates": date_str},
            )
        except Exception as e:
            log.warning("World Cup fetch failed for %s: %s", date_str, e)
            cur += timedelta(days=1)
            continue

        for ev in data.get("events", []):
            ev_id = ev.get("id")
            if ev_id in seen_event_ids:
                continue
            seen_event_ids.add(ev_id)

            comp = ev.get("competitions", [{}])[0]
            start_iso = comp.get("date") or ev.get("date")
            if not start_iso:
                continue

            competitors = comp.get("competitors", [])
            home = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away = next((c for c in competitors if c.get("homeAway") == "away"), {})
            home_name = home.get("team", {}).get("displayName", "?")
            away_name = away.get("team", {}).get("displayName", "?")

            # Stage detection
            slug = ev.get("season", {}).get("slug", "") or ""
            notes = comp.get("notes", []) or []
            stage_text = ""
            for n in notes:
                if n.get("type") == "event":
                    stage_text = n.get("headline", "")
                    break

            is_knockout = any(k.lower() in (slug + " " + stage_text).lower()
                              for k in ["round-of", "quarter", "semi", "final", "third"])

            include = False
            if home_name in selected or away_name in selected:
                include = True
            if knockout_all and is_knockout:
                include = True

            if not include:
                continue

            try:
                start_utc = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            except Exception:
                continue

            zh_home = _wc_zh(home_name)
            zh_away = _wc_zh(away_name)
            # 階段標籤：先看 slug，再看 stage_text
            slug_low = (slug or "").lower()
            label = ""
            if "round-of-32" in slug_low:
                label = "（32 強）"
            elif "round-of-16" in slug_low or "rd-of-16" in slug_low:
                label = "（16 強）"
            elif "quarter" in slug_low:
                label = "（8 強）"
            elif "semi" in slug_low:
                label = "（4 強）"
            elif "third-place" in slug_low or "3rd-place" in slug_low:
                label = "（季軍賽）"
            elif slug_low == "final" or slug_low.endswith("/final"):
                label = "（冠軍賽）"
            elif "group" in slug_low:
                label = "（小組賽）"
            elif stage_text:
                label = f"（{stage_text}）"

            # 把使用者選擇的隊伍放前面，方便在行事曆視覺上一眼識別
            if away_name in selected:
                summary = f"⚽ 世界杯｜{zh_away} vs {zh_home}{label}"
            elif home_name in selected:
                summary = f"⚽ 世界杯｜{zh_home} vs {zh_away}{label}"
            else:
                # 純淘汰賽（knockout_all 觸發）：用 home vs away
                summary = f"⚽ 世界杯｜{zh_home} vs {zh_away}{label}"
            venue = comp.get("venue", {}).get("fullName", "")
            uid = make_uid("wc", ev_id)
            events.append(make_event(
                uid, start_utc, 120,
                summary,
                location=venue,
                description=f"{away_name} vs {home_name}",
            ))

        cur += timedelta(days=1)

    log.info("World Cup: %d events", len(events))
    return events


# ---------------- VNL (Volleyball Nations League) ----------------

# 排球國家名中文對照（重用 WC_ZH 已有的，再補常見排球隊）
VNL_ZH_EXTRA = {
    "United States": "美國", "Dominican Republic": "多明尼加",
    "Czech Republic": "捷克", "Netherlands": "荷蘭", "Poland": "波蘭",
    "Bulgaria": "保加利亞", "Italy": "義大利", "Turkey": "土耳其",
    "Serbia": "塞爾維亞", "Slovenia": "斯洛維尼亞", "Ukraine": "烏克蘭",
    "Iran": "伊朗", "China": "中國", "Cuba": "古巴",
    "Belgium": "比利時", "Argentina": "阿根廷", "France": "法國",
    "Germany": "德國", "Canada": "加拿大", "Brazil": "巴西",
    "Japan": "日本", "Thailand": "泰國", "Australia": "澳洲",
}


def _vnl_zh(name):
    return VNL_ZH_EXTRA.get(name, WC_ZH.get(name, name))


def fetch_vnl(cfg):
    """讀 data/vnl_{season}.yaml，依 teams 過濾出關心的場次。"""
    if not cfg.get("enabled"):
        return []

    season = cfg.get("season", 2026)
    data_path = ROOT / "data" / f"vnl_{season}.yaml"
    if not data_path.exists():
        log.warning("VNL data file not found: %s", data_path)
        return []

    try:
        data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("VNL data parse failed: %s", e)
        return []

    men_teams = set(cfg.get("teams", {}).get("men", []) or [])
    women_teams = set(cfg.get("teams", {}).get("women", []) or [])

    events = []
    seen_uids = set()
    for m in data.get("matches", []) or []:
        gender = m.get("gender", "").lower()
        home = m.get("home", "")
        away = m.get("away", "")
        selected = men_teams if gender == "men" else women_teams
        if home not in selected and away not in selected:
            continue

        # Parse local time and convert to UTC
        tz_name = m.get("tz", "UTC")
        try:
            tz = ZoneInfo(tz_name)
            local_dt = datetime.fromisoformat(f"{m['date']}T{m['time']}").replace(tzinfo=tz)
            start_utc = local_dt.astimezone(UTC)
        except Exception as e:
            log.warning("VNL time parse failed for %s vs %s (%s): %s", home, away, m.get("date"), e)
            continue

        zh_home = _vnl_zh(home)
        zh_away = _vnl_zh(away)
        gender_zh = "男排" if gender == "men" else "女排"

        # 把選擇的隊伍放前面，方便識別
        if away in selected and home not in selected:
            summary = f"🏐 VNL {gender_zh}｜{zh_away} vs {zh_home}"
        elif home in selected and away not in selected:
            summary = f"🏐 VNL {gender_zh}｜{zh_home} vs {zh_away}"
        else:
            # 兩隊都是選擇的（例如 日本 vs 巴西）
            summary = f"🏐 VNL {gender_zh}｜{zh_home} vs {zh_away}"

        venue = m.get("venue", "")
        uid = make_uid("vnl", season, gender, m["date"], m["time"], home, away)
        if uid in seen_uids:
            continue
        seen_uids.add(uid)

        events.append(make_event(
            uid, start_utc, 150,  # ~2.5h
            summary,
            location=venue,
            description=f"{home} vs {away}",
        ))

    log.info("VNL: %d events", len(events))
    return events


# ---------------- Diff / Change summary ----------------
#
# docs/sports.ics 現在是賽事資料的純函數（DTSTAMP 固定＝賽事開始時間），
# 所以 git diff 本身已經不會再有假陽性。但我們仍然想要一段「人類可讀」的
# 異動摘要給 Telegram 通知用，所以在覆寫檔案之前，比對新舊兩份 ics 的內容，
# 產生新增 / 異動 / 移除清單，寫到 diff_summary.txt。


def _uid_of(ev):
    v = ev.get("uid")
    return str(v) if v is not None else None


def _normalize_dt(value):
    """把 icalendar 解析出來的 datetime（可能 naive、可能不同 tzinfo 實作）
    統一轉成 UTC-aware datetime 再比較，避免時區表示法不同造成假陽性。"""
    if value is None:
        return None
    dt = getattr(value, "dt", value)
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    return dt  # 純 date（理論上這個專案不會用到）


def _event_fields(ev):
    """取出除了 DTSTAMP 以外的全部欄位，欄位不存在一律用 None 表示。"""

    def _str(key):
        v = ev.get(key)
        return str(v) if v is not None else None

    def _dt(key):
        v = ev.get(key)
        if v is None:
            return None
        return _normalize_dt(v.dt)

    return {
        "summary": _str("summary"),
        "dtstart": _dt("dtstart"),
        "dtend": _dt("dtend"),
        "location": _str("location"),
        "description": _str("description"),
    }


def load_old_calendar():
    """讀現有的 docs/sports.ics。不存在就當作舊檔是空的（全部算新增）。"""
    try:
        raw = OUT_PATH.read_bytes()
    except FileNotFoundError:
        return None
    try:
        return Calendar.from_ical(raw)
    except Exception as e:
        log.warning("Failed to parse existing %s, treat as empty: %s", OUT_PATH, e)
        return None


def build_fields_map(events):
    result = {}
    for ev in events:
        uid = _uid_of(ev)
        if uid is None:
            continue
        result[uid] = _event_fields(ev)
    return result


def compute_diff(old_fields, new_fields):
    old_uids = set(old_fields)
    new_uids = set(new_fields)
    added = sorted(new_uids - old_uids)
    removed = sorted(old_uids - new_uids)
    changed = sorted(
        uid for uid in (old_uids & new_uids)
        if old_fields[uid] != new_fields[uid]
    )
    return added, removed, changed


def pair_vnl_reschedules(added, removed, old_fields, new_fields):
    """VNL 的 UID 含比賽日期時間，改期會讓 UID 整個換掉，變成「移除一場+
    新增一場」。這裡把兩邊都是 VNL、且 SUMMARY 球隊組合相同的配對挑出來，
    合併成一則「改期」訊息。其他運動用穩定 ID（game_pk / event_id / round_no /
    ev_id），不會有這個問題，不需要處理。"""
    removed_pool = defaultdict(list)
    for uid in removed:
        summ = old_fields[uid]["summary"] or ""
        if summ.startswith("🏐 VNL"):
            removed_pool[summ].append(uid)

    rescheduled = []  # (old_uid, new_uid, summary)
    consumed_added = set()
    consumed_removed = set()
    for uid in added:
        summ = new_fields[uid]["summary"] or ""
        if not summ.startswith("🏐 VNL"):
            continue
        pool = removed_pool.get(summ)
        if pool:
            old_uid = pool.pop(0)
            rescheduled.append((old_uid, uid, summ))
            consumed_added.add(uid)
            consumed_removed.add(old_uid)

    added_remaining = [u for u in added if u not in consumed_added]
    removed_remaining = [u for u in removed if u not in consumed_removed]
    return added_remaining, removed_remaining, rescheduled


def _fmt_dt(dt):
    if dt is None:
        return "?"
    return dt.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M")


def build_diff_message(added, removed, changed, rescheduled, old_fields, new_fields):
    # entries: (is_item, text)。is_item=False 是段落標題，不計入「場」數。
    entries = []

    if rescheduled:
        entries.append((False, f"🔄 改期 {len(rescheduled)} 場："))
        for old_uid, new_uid, summ in rescheduled:
            old_dt = _fmt_dt(old_fields[old_uid]["dtstart"])
            new_dt = _fmt_dt(new_fields[new_uid]["dtstart"])
            entries.append((True, f"  {summ}：{old_dt} → {new_dt}"))

    if changed:
        entries.append((False, f"✏️ 異動 {len(changed)} 場："))
        for uid in changed:
            summ = new_fields[uid]["summary"] or "?"
            dt = _fmt_dt(new_fields[uid]["dtstart"])
            entries.append((True, f"  {summ}（{dt}）"))

    if added:
        entries.append((False, f"🆕 新增 {len(added)} 場："))
        for uid in added:
            summ = new_fields[uid]["summary"] or "?"
            dt = _fmt_dt(new_fields[uid]["dtstart"])
            entries.append((True, f"  {summ}（{dt}）"))

    if removed:
        entries.append((False, f"🗑️ 移除 {len(removed)} 場："))
        for uid in removed:
            summ = old_fields[uid]["summary"] or "?"
            dt = _fmt_dt(old_fields[uid]["dtstart"])
            entries.append((True, f"  {summ}（{dt}）"))

    if not entries:
        return "本次無異動。"

    total_items = sum(1 for is_item, _ in entries if is_item)
    full_text = "\n".join(t for _, t in entries)
    if len(full_text) <= DIFF_SUMMARY_CHAR_LIMIT:
        return full_text

    kept_lines = []
    kept_items = 0
    cur_len = 0
    budget = DIFF_SUMMARY_CHAR_LIMIT - DIFF_SUMMARY_SUFFIX_RESERVE
    for is_item, t in entries:
        add_len = len(t) + (1 if kept_lines else 0)
        if cur_len + add_len > budget:
            break
        kept_lines.append(t)
        cur_len += add_len
        if is_item:
            kept_items += 1

    remaining = total_items - kept_items
    kept_lines.append(
        f"...（還有 {remaining} 場，內容過長未列出，完整清單看 GitHub commit diff）"
    )
    return "\n".join(kept_lines)


def write_diff_summary(text):
    runner_temp = os.environ.get("RUNNER_TEMP", "/tmp")
    out = Path(runner_temp) / "diff_summary.txt"
    out.write_text(text, encoding="utf-8")
    log.info("Diff summary written to %s (%d chars)", out, len(text))
    return out


# ---------------- Main ----------------

def main():
    cfg_path = ROOT / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    tz_name = cfg.get("timezone", "Asia/Taipei")
    log.info("Display timezone: %s (events stored as UTC, Apple Calendar will convert)", tz_name)

    # 寫檔之前先讀舊的 .ics，供產生異動摘要用
    old_cal = load_old_calendar()
    old_events = old_cal.walk("VEVENT") if old_cal is not None else []
    old_fields = build_fields_map(old_events)

    cal = Calendar()
    cal.add("prodid", "-//Sports Calendar//ZH-TW//")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "運動賽事訂閱 (NBA/MLB/F1/世界杯)")
    cal.add("x-wr-timezone", tz_name)
    cal.add("x-wr-caldesc", "自動產生的賽程訂閱檔 — 修改 config.yaml 即可變更追蹤對象")

    season = date.today().year

    all_events = []
    all_events += fetch_mlb(cfg.get("mlb", {}), season)
    all_events += fetch_nba(cfg.get("nba", {}))
    all_events += fetch_f1(cfg.get("f1", {}))
    all_events += fetch_worldcup(cfg.get("worldcup", {}))
    all_events += fetch_vnl(cfg.get("vnl", {}))

    for ev in all_events:
        cal.add_component(ev)

    # 比對新舊內容，產生異動摘要（不影響是否寫檔——永遠正常覆寫）
    new_fields = build_fields_map(all_events)
    added, removed, changed = compute_diff(old_fields, new_fields)
    added, removed, rescheduled = pair_vnl_reschedules(added, removed, old_fields, new_fields)
    diff_msg = build_diff_message(added, removed, changed, rescheduled, old_fields, new_fields)
    write_diff_summary(diff_msg)
    log.info(
        "Diff: %d added, %d removed, %d changed, %d rescheduled",
        len(added), len(removed), len(changed), len(rescheduled),
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_bytes(cal.to_ical())
    log.info("Wrote %d events to %s", len(all_events), OUT_PATH)


if __name__ == "__main__":
    main()
