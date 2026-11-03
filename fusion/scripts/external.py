# -*- coding: utf-8 -*-
"""룩어라이크 외부 데이터(fusion/external/) — 니모트론 인물 1명 → 같은 조건 셀(성·연령대·취업·가구)의 집계 실측.
정량 매칭이 없다 — 셀은 니모트론 원본 필드(sex·age·economic_activity_status·family_type·region)로 만든다.

    import external as X
    cell = X.cell_of(person)                        # panel.json 인물(raw 51컬럼) → {"sex","age","age_band","emp","hh","region"}
    X.available()                                   # {"time_use": True, "media_panel": False, "naver_datalab": True}
    X.time_minutes(cell, "간식 및 음료")            # 성×연령대 하루 평균 분 (by="emp"면 성×취업, 요일별)
    X.time_clock(cell, "기상", "평일")               # 기상·취침·식사 시작 평균 시각
    X.time_slots(cell, daytype="평일")              # 시간대별 행위자 비율 (취업자 '일' 30분 단위 + 전 국민 상위 행동)
    X.media(cell)                                   # 미디어 이용 지표
    X.datalab(cell, group="저가 커피")              # 검색 상대지수(성×연령코드)
태그: [X:생활시간] / [X:미디어패널] / [X:데이터랩] — 모두 집단 실측이다. 개인 사실로 쓰지 않는다.
"""
import os, pathlib, csv, json

_HERE = pathlib.Path(__file__).resolve().parent
DATASETS = {"time_use": ("time_use_slots.csv", "time_use_minutes.csv", "time_use_clock.csv"), "media_panel": ("media_use.csv",),
            "naver_datalab": ("search_trend.csv", "shopping.csv")}
TAGS = {"time_use": "[X:생활시간]", "media_panel": "[X:미디어패널]", "naver_datalab": "[X:데이터랩]"}
NAVER_AGE = {(0, 12): "1", (13, 18): "2", (19, 24): "3", (25, 29): "4", (30, 34): "5", (35, 39): "6", (40, 44): "7",
             (45, 49): "8", (50, 54): "9", (55, 59): "10", (60, 200): "11"}


def ext_dir():
    d = os.environ.get("NEMO_EXTERNAL_DIR")
    return pathlib.Path(d) if d else _HERE.parent / "external"


def available():
    return {k: any((ext_dir() / k / f).exists() for f in fs) for k, fs in DATASETS.items()}


def _band(a):
    return "10대" if a < 20 else ("60대+" if a >= 60 else f"{a // 10 * 10}대")


def naver_age_code(age):
    return next(v for (lo, hi), v in NAVER_AGE.items() if lo <= age <= hi)


def hh_of(family_type):
    """니모트론 family_type → 생활시간 표의 가구 셀(1인/부부/부부+자녀/부모동거/기타)."""
    f = str(family_type or "")
    if not f: return None
    if f.startswith("혼자 거주"): return "1인"
    if f.startswith("배우자·자녀") and "부모" not in f and "어머니" not in f and "아버지" not in f: return "부부+자녀"
    if f == "배우자와 거주": return "부부"
    if "배우자" not in f and any(k in f for k in ("부모", "어머니", "아버지", "부 또는 모")): return "부모동거"
    return "기타"


def cell_of(person):
    """니모트론 원본 필드 기준 셀. emp = economic_activity_status(취업자 → 취업, 실업자·비경제활동인구 → 비취업)."""
    raw = person["raw"]
    age = int(raw["age"])
    ea = str(raw.get("economic_activity_status") or "")
    emp = None if not ea else ("취업" if ea == "취업자" else "비취업")
    return {"sex": "여" if str(raw.get("sex", "")).startswith("여") else "남", "age": age, "age_band": _band(age), "emp": emp,
            "hh": hh_of(raw.get("family_type")), "region": str(raw.get("region", ""))}


def _read(ds, fname):
    p = ext_dir() / ds / fname
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


CELL_KEYS = ("sex", "age_band", "emp", "hh")


def _match(rows, cell, keys_order):
    """keys_order의 앞 조합부터 정확히 그 키들만 채워진 행을 찾는다(나머지 셀 키는 빈 값). 없으면 다음 조합.
    () 조합 = 전 국민 행. 반환 행에 'cell'(실제 쓴 셀) 추가."""
    for keys in keys_order:
        hit = [dict(r) for r in rows if all(cell.get(k) and r.get(k) == cell.get(k) for k in keys)
               and all(not r.get(k) for k in CELL_KEYS if k not in keys)]
        if hit:
            label = "×".join(str(cell[k]) for k in keys) or "전 국민"
            for r in hit: r["cell"] = label
            return hit
    return []


BY_AGE = (("sex", "age_band"), ("age_band",), ())
BY_EMP = (("sex", "emp"), ("emp",), ())


def time_minutes(cell, activity=None, by="age", daytype=None):
    """행동별 하루 평균 분. by='age' → 성×연령대(표 2-1, 요일평균) · by='emp' → 성×취업 여부(표 7-1/7-2, 요일별)."""
    rows = _match(_read("time_use", "time_use_minutes.csv"), cell, BY_AGE if by == "age" else BY_EMP)
    return [r for r in rows if (not activity or activity in r["activity"]) and (not daytype or r["daytype"] == daytype)]


def time_clock(cell, event=None, daytype=None):
    """기상·취침·식사 시작 평균 시각. 표가 성별 또는 연령별로만 나뉘어 있어 연령대 행 → 성별 행 → 전체 순."""
    rows = _match(_read("time_use", "time_use_clock.csv"), cell, (("age_band",), ("sex",), ()))
    return [r for r in rows if (not event or event in r["event"]) and (not daytype or r["daytype"] == daytype)]


def time_slots(cell, activity=None, daytype=None):
    """시간대별 행위자 비율. 취업자면 성×취업의 30분 단위 '일' 행위자 비율(표 7-4), 그 외엔 전 국민 시간대별 상위 3 행동."""
    rows = _read("time_use", "time_use_slots.csv")
    out = _match([r for r in rows if r.get("emp")], cell, (("sex", "emp"), ("emp",))) if cell.get("emp") == "취업" else []
    out += _match([r for r in rows if not r.get("emp")], cell, ((),))
    return [r for r in out if (not activity or activity in r["activity"]) and (not daytype or r["daytype"] == daytype)]


def media(cell, item=None):
    rows = _match(_read("media_panel", "media_use.csv"), cell, (("sex", "age_band", "emp", "hh"), ("sex", "age_band", "emp"), BY_AGE[0], BY_AGE[1]))
    return [r for r in rows if not item or item in r.get("item", "")]


def datalab(cell, group=None, path=None):
    """검색 상대지수(성×네이버 연령코드). path를 주면 그 CSV(브리프 키워드 수집분)를 읽는다."""
    code = naver_age_code(cell["age"])
    src = _read_path(path) if path else _read("naver_datalab", "search_trend.csv")
    rows = [r for r in src if r.get("age_code") in (code, "")
            and r.get("gender") in ({"남": "m", "여": "f"}[cell["sex"]], "")]
    return [r for r in rows if not group or group in r.get("group", "")]


def _read_path(path):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- Apify 데이터랩 수집 (Apify가 연결된 세션만 · 비용 고지·승인 후)
APIFY_DATALAB_ACTOR = "automation-lab/naver-datalab-search-trends-scraper"
ANCHOR = {"name": "커피", "keywords": ["커피", "카페"]}   # 저장소 기본 파일의 앵커. 브리프 수집 땐 카테고리 대표어로 바꿔 넘긴다(anchor=)
AGE_RANGE = {"3": "19~24", "4": "25~29", "5": "30~34", "6": "35~39", "7": "40~44", "8": "45~49", "9": "50~54", "10": "55~59", "11": "60+"}


def panel_datalab_cells(panel_json):
    """패널 인물들의 (성, 네이버 연령코드) 고유 조합 — 브리프 키워드는 이 칸만 수집한다(전 칸 18회 대신)."""
    d = json.load(open(panel_json, encoding="utf-8"))
    out = set()
    for s in d["segments"]:
        for p in s["personas"]:
            c = cell_of(p)
            out.add(({"남": "m", "여": "f"}[c["sex"]], naver_age_code(c["age"])))
    return sorted(out)


def apify_datalab_input(groups, gender, age_code, start, end, time_unit="month", anchor=None):
    """Apify 액터 입력. groups = [{"name","keywords"}] 최대 4개 — 앵커(카테고리 대표어)를 앞에 붙여 5그룹."""
    assert 1 <= len(groups) <= 4, "브리프 키워드 그룹은 1~4개(앵커 포함 5개 한도)"
    return {"keywordGroups": [anchor or ANCHOR] + list(groups), "startDate": start, "endDate": end, "timeUnit": time_unit,
            "gender": gender, "ages": [age_code]}


def apify_items_to_rows(items, gender, age_code, start, end, source_note, anchor_name=None):
    """get-dataset-items 결과(keywordGroup·period·ratio) → search_trend.csv 형식 행(vs_anchor 포함)."""
    anchor = {it["period"]: float(it["ratio"]) for it in items if it["keywordGroup"] == (anchor_name or ANCHOR["name"])}
    rows = []
    for it in items:
        a = anchor.get(it["period"])
        rows.append({"group": it["keywordGroup"], "gender": gender, "age_code": age_code, "age_range": AGE_RANGE.get(age_code, ""),
                     "period": it["period"], "ratio": it["ratio"], "vs_anchor": round(float(it["ratio"]) / a, 4) if a else "",
                     "startDate": start, "endDate": end, "source": source_note})
    return rows


def write_rows(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return path


def datalab_freshness():
    """저장소 기본 파일의 수집 종료일 → (endDate, 경과 일수). 45일 넘으면 갱신 제안 대상."""
    import datetime
    rows = _read("naver_datalab", "search_trend.csv")
    if not rows:
        return None, None
    end = max(r["endDate"] for r in rows)
    days = (datetime.date.today() - datetime.date.fromisoformat(end)).days
    return end, days


def shopping(cell, category=None):
    rows = _match(_read("naver_datalab", "shopping.csv"), cell, BY_AGE)
    return [r for r in rows if not category or category in r.get("category", "")]


if __name__ == "__main__":
    print(ext_dir(), available())


# ---------------------------------------------------------------- Apify 소셜 — 인스타 해시태그 · 유튜브 검색 (패널 실행마다, 승인 후)
# 둘 다 성·연령 정보가 없다 → 룩어라이크 '셀' 실측이 아니라 세그·브리프 수준의 '지금 SNS에서 실제로 돌아다니는 것'.
# 개인 식별 정보(계정명·본문 원문)는 저장하지 않고 집계만 남긴다.
IG_ACTOR = "apify/instagram-hashtag-scraper"      # 결과당 약 $0.0026 (무료 플랜은 해시태그당 첫 페이지만)
YT_ACTOR = "streamers/youtube-scraper"            # 영상당 약 $0.004
AD_MARKERS = ("광고", "협찬", "유료광고", "#ad", "sponsored", "체험단", "제공받아", "원고료", "이벤트", "오픈", "가맹", "창업", "매장 안내")
# 인스타 해시태그·유튜브 검색은 브리프 카테고리·브랜드 시드로 실행마다 정한다(예: 커피면 #저가커피 / 화장품이면 #올리브영추천).
import re as _re
from collections import Counter as _C


def ig_input(hashtags, limit=25, reels=False):
    return {"hashtags": [h.lstrip("#") for h in hashtags], "resultsType": "reels" if reels else "posts", "resultsLimit": limit}


def yt_input(queries, limit=20, shorts=10):
    return {"searchQueries": list(queries), "maxResults": limit, "maxResultsShorts": shorts, "maxResultStreams": 0}


def _is_ad(text, owner=""):
    t = (text or "").lower()
    return any(m.lower() in t for m in AD_MARKERS) or any(k in (owner or "").lower() for k in ("official", "store", "cafe_", "coffee_"))


def _hour(ts):
    """UTC 타임스탬프 → 한국 시각(시)."""
    m = _re.search(r"T(\d\d):", str(ts or ""))
    return (int(m.group(1)) + 9) % 24 if m else None


def instagram_summary(items, seeds, source_note):
    """해시태그 게시물 → 집계(개인 정보 없음). 광고·매장 발신은 따로 세고 소비자 발신 기준으로 요약."""
    seeds = {s.lstrip("#").lower() for s in seeds}
    con = [it for it in items if not _is_ad(it.get("caption"), it.get("ownerUsername"))]
    ads = len(items) - len(con)
    co = _C(h.lower() for it in con for h in (it.get("hashtags") or []) if h and h.lower() not in seeds)
    types = _C(("릴스" if it.get("productType") == "clips" else {"Image": "사진", "Video": "영상", "Sidecar": "여러 장"}.get(it.get("type"), it.get("type") or "?")) for it in con)
    likes = sorted(int(it.get("likesCount") or 0) for it in con if (it.get("likesCount") or -1) >= 0)
    hrs = _C(_hour(it.get("timestamp")) for it in con if _hour(it.get("timestamp")) is not None)
    words = _C(w for it in con for w in _re.findall(r"[가-힣]{2,}", _re.sub(r"#\S+", " ", it.get("caption") or "")))
    stop = {"오늘", "그리고", "진짜", "너무", "정말", "있는", "하는", "에서", "으로", "합니다", "입니다", "있어요", "했어요"}
    dates = sorted(str(it.get("timestamp", ""))[:10] for it in items if it.get("timestamp"))
    return {"dataset": "instagram", "tag": "[X:인스타]", "seeds": sorted(seeds), "n_posts": len(items), "n_consumer": len(con), "n_ad_or_store": ads,
            "period": f"{dates[0]}~{dates[-1]}" if dates else "", "content_type_share": {k: round(v / max(len(con), 1), 2) for k, v in types.most_common()},
            "top_cohashtags": [h for h, _ in co.most_common(15)], "caption_keywords": [w for w, _ in words.most_common(40) if w not in stop][:15],
            "median_likes": likes[len(likes) // 2] if likes else None, "post_hours_top": [h for h, _ in hrs.most_common(4)], "source": source_note}


def youtube_summary(items, queries, source_note):
    """유튜브 검색 결과 → 집계. 채널명은 공개 크리에이터·브랜드라 상위 몇 개만 남긴다."""
    vids = [it for it in items if it.get("title")]
    def views(it):
        try: return int(it.get("viewCount") or 0)
        except Exception: return 0
    shorts = [it for it in vids if "/shorts/" in str(it.get("url", "")) or str(it.get("type", "")).lower() == "shorts"]
    words = _C(w for it in vids for w in _re.findall(r"[가-힣A-Za-z]{2,}", it["title"]))
    q = {w for s in queries for w in s.split()}
    top = sorted(vids, key=views, reverse=True)[:10]
    dates = sorted(str(it.get("date", ""))[:10] for it in vids if it.get("date"))
    vv = sorted(views(it) for it in vids)
    return {"dataset": "youtube", "tag": "[X:유튜브]", "queries": list(queries), "n_videos": len(vids), "shorts_share": round(len(shorts) / max(len(vids), 1), 2),
            "period": f"{dates[0]}~{dates[-1]}" if dates else "", "median_views": vv[len(vv) // 2] if vv else None,
            "title_keywords": [w for w, _ in words.most_common(40) if w not in q][:15],
            "top_titles": [{"title": it["title"][:80], "views": views(it), "channel": it.get("channelName", "")} for it in top],
            "top_channels": [c for c, _ in _C(it.get("channelName", "") for it in vids if it.get("channelName")).most_common(8)], "source": source_note}


def save_social(summary, outdir):
    p = pathlib.Path(outdir) / f"social_{summary['dataset']}.json"
    json.dump(summary, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return str(p)


def load_social(outdir):
    out = {}
    for ds in ("instagram", "youtube"):
        p = pathlib.Path(outdir) / f"social_{ds}.json"
        if p.exists():
            out[ds] = json.load(open(p, encoding="utf-8"))
    return out


# ---------------------------------------------------------------- 떠오르는 콘텐츠 풀 (유튜브 차트 · 인스타 관심사 해시태그 · 틱톡 급상승) → 인물 rising_feed
YT_CHART_ACTOR = "maximedupre/youtube-trending-videos-scraper"   # 무료 · 유튜브 운영 카테고리 페이지·차트(지역별)
YT_CHART_SOURCES = ["musicTrending", "musicCharts", "gamingTrending", "sportsTrending", "newsTrending", "fashionTrending",
                    "learningTrending", "podcastsTrending", "shoppingTrending", "moviesTrending"]
TT_ACTOR = "datapeak/tiktok-creative-center"                     # 급상승 해시태그 건당 약 $0.001 · 쿠키 불필요 · RESIDENTIAL 프록시
SOURCE_KO = {"musicTrending": "음악", "musicCharts": "음악 차트", "gamingTrending": "게임", "sportsTrending": "스포츠", "newsTrending": "뉴스",
             "fashionTrending": "패션", "learningTrending": "학습", "podcastsTrending": "팟캐스트", "shoppingTrending": "쇼핑", "moviesTrending": "영화"}
RISING_TAGS = {"[X:유튜브·급상승]": "youtube_charts", "[X:인스타·급상승]": "instagram_rising", "[X:틱톡·급상승]": "tiktok_trends"}
PLATFORM_SNS = {"유튜브": "유튜브", "인스타": "인스타그램", "틱톡": "틱톡"}   # rising_feed.platform → fused.sns_use.platforms 이름
SNS_PLATFORMS = ("유튜브", "인스타그램", "틱톡", "블로그", "페이스북", "X", "스레드", "카카오스토리", "커뮤니티", "네이버 카페")
# 관심사 단어 → 인스타 시드 해시태그 (니모트론 취미·식생활·여가 서술에서 매칭)
INTEREST_TAGS = {"카페": ["카페투어", "카공"], "맛집": ["맛집탐방"], "요리": ["집밥", "레시피"], "베이킹": ["홈베이킹"], "운동": ["오운완"],
                 "헬스": ["오운완", "헬스"], "러닝": ["러닝", "러닝크루"], "등산": ["등산"], "요가": ["요가"], "필라테스": ["필라테스"],
                 "골프": ["골프"], "캠핑": ["캠핑"], "여행": ["국내여행"], "드라이브": ["드라이브"], "독서": ["책스타그램"], "영화": ["영화추천"],
                 "드라마": ["드라마추천"], "OTT": ["넷플릭스추천"], "게임": ["게임"], "음악": ["플레이리스트"], "공연": ["콘서트"],
                 "사진": ["사진스타그램"], "패션": ["데일리룩"], "쇼핑": ["쇼핑하울"], "뷰티": ["데일리메이크업"], "반려": ["멍스타그램"],
                 "강아지": ["멍스타그램"], "고양이": ["냥스타그램"], "육아": ["육아스타그램"], "편의점": ["편의점신상"], "디저트": ["디저트맛집"],
                 "혼술": ["혼술"], "소주": ["혼술"], "맥주": ["혼술"], "와인": ["와인스타그램"], "전시": ["전시회"], "공부": ["공스타그램"], "자기계발": ["갓생"], "인테리어": ["집꾸미기"]}


INTEREST_FIELDS = ("hobbies_and_interests", "hobbies_and_interests_list", "culinary_persona", "sports_persona", "arts_persona",
                   "travel_persona", "persona", "detailed_persona")


def interest_terms(person):
    """인물 관심사 텍스트 — 니모트론 취미·식생활·여가·예술·여행 서술. rising_feed.match는 이 안에 실재해야 한다."""
    raw = person.get("raw", {})
    return " ".join(str(raw.get(k, "")) for k in INTEREST_FIELDS)


def person_seed_tags(person):
    t = interest_terms(person)
    return sorted({h for k, hs in INTEREST_TAGS.items() if k in t for h in hs})


def panel_interest_seeds(panel_json, max_tags=8):
    """패널 전체의 인스타 시드 해시태그 — 인물 수가 많은 관심사부터."""
    d = json.load(open(panel_json, encoding="utf-8"))
    c = _C(h for s in d["segments"] for p in s["personas"] for h in person_seed_tags(p))
    return [h for h, _ in c.most_common(max_tags)]


def yt_chart_input(sources=None, n=20, region="KR"):
    return {"regions": [region], "sources": sources or YT_CHART_SOURCES, "maxResultsPerSourceRegion": n}


def tt_input(period="7", n=50, region="KR"):
    return {"mode": "hashtags", "region": region, "period": period, "maxItems": n,
            "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]}}


def _num(x):
    try: return int(str(x).replace(",", ""))
    except Exception: return 0


def youtube_charts_summary(items, source_note):
    """유튜브 카테고리 차트 → 카테고리별 상위 영상(제목·채널·순위·조회수). 성·연령 없음."""
    by = {}
    for it in items:
        src = it.get("source") or it.get("sourceKey") or it.get("sourceLabel") or "?"
        by.setdefault(SOURCE_KO.get(src, src), []).append({"rank": it.get("rank") or it.get("position"), "title": str(it.get("title", ""))[:90],
                                                            "channel": it.get("channelTitle") or it.get("channelName") or "",
                                                            "views": _num(it.get("viewCount") or it.get("views"))})
    for k in by: by[k] = sorted(by[k], key=lambda r: (r["rank"] is None, r["rank"] or 0))[:15]
    words = _C(w for v in by.values() for r in v for w in _re.findall(r"[가-힣A-Za-z]{2,}", r["title"]))
    return {"dataset": "youtube_charts", "tag": "[X:유튜브·급상승]", "region": "KR", "by_category": by,
            "title_keywords": [w for w, _ in words.most_common(30)], "source": source_note}


def instagram_rising_summary(items, seeds, source_note, recent_days=7):
    """관심사 시드 해시태그 게시물 → '최근 7일에 몰리는' 동반 해시태그(떠오름 대리 지표)와 시간당 반응 높은 형식. 진짜 급상승 순위가 아니다."""
    import datetime as _dt
    seeds_l = {s.lstrip("#").lower() for s in seeds}
    ts = [_dt.datetime.fromisoformat(str(it["timestamp"]).replace("Z", "+00:00")) for it in items if it.get("timestamp")]
    now = max(ts) if ts else None
    con = [it for it in items if not _is_ad(it.get("caption"), it.get("ownerUsername")) and it.get("timestamp")]
    rec, old, seed_of = _C(), _C(), {}
    eng = {}
    for it in con:
        t = _dt.datetime.fromisoformat(str(it["timestamp"]).replace("Z", "+00:00"))
        age_h = max((now - t).total_seconds() / 3600, 1)
        tags = [h.lower() for h in (it.get("hashtags") or []) if h]
        seed = next((h for h in tags if h in seeds_l), None)
        for h in tags:
            if h in seeds_l: continue
            (rec if age_h <= recent_days * 24 else old)[h] += 1
            if seed: seed_of.setdefault(h, seed)
        fmt = "릴스" if it.get("productType") == "clips" else {"Image": "사진", "Video": "영상", "Sidecar": "여러 장"}.get(it.get("type"), "기타")
        eng.setdefault(fmt, []).append((int(it.get("likesCount") or 0) + int(it.get("commentsCount") or 0)) / age_h)
    rising = [{"hashtag": h, "recent": n, "older": old[h], "recent_share": round(n / (n + old[h]), 2), "seed": seed_of.get(h, "")}
              for h, n in rec.items() if n >= 2 and n / (n + old[h]) >= 0.6]
    rising.sort(key=lambda r: (-r["recent"], -r["recent_share"]))
    fmt = {k: round(sorted(v)[len(v) // 2], 2) for k, v in eng.items() if v}
    return {"dataset": "instagram_rising", "tag": "[X:인스타·급상승]", "seeds": sorted(seeds_l), "n_posts": len(items), "n_consumer": len(con),
            "window": f"최근 {recent_days}일 vs 이전", "rising_hashtags": rising[:25], "engagement_per_hour_by_format": fmt,
            "note": "떠오름 = 최근 7일 쏠림(대리 지표). 인스타 공식 급상승 순위 아님. 무료 플랜은 해시태그당 첫 페이지만.", "source": source_note}


def tiktok_trends_summary(items, source_note):
    """틱톡 크리에이티브 센터 한국 급상승 해시태그. 연령 분포 필드가 있으면 남긴다(인물 연령대 매칭에 씀)."""
    out = []
    for it in items:
        name = it.get("hashtag_name") or it.get("hashtagName") or it.get("hashtag") or it.get("name")
        if not name: continue
        ages = it.get("audience_ages") or it.get("audienceAges") or it.get("audience_age") or []
        ages = [str(a.get("age_level") or a.get("ageLevel") or a.get("age") or a) for a in ages] if isinstance(ages, list) else []
        out.append({"hashtag": str(name).lstrip("#"), "rank": it.get("rank"), "rank_change": it.get("rank_diff") or it.get("rankDiff") or it.get("rankChange"),
                    "posts": _num(it.get("publish_cnt") or it.get("publishCnt") or it.get("posts")), "views": _num(it.get("video_views") or it.get("videoViews") or it.get("views")),
                    "industry": (it.get("industry_info") or {}).get("value") if isinstance(it.get("industry_info"), dict) else it.get("industry"),
                    "audience_ages": ages})
    return {"dataset": "tiktok_trends", "tag": "[X:틱톡·급상승]", "region": "KR", "hashtags": out[:60],
            "has_age": any(r["audience_ages"] for r in out), "source": source_note}


def save_rising(summary, outdir):
    p = pathlib.Path(outdir) / f"rising_{summary['dataset']}.json"
    json.dump(summary, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return str(p)


def load_rising(outdir):
    out = {}
    for ds in ("youtube_charts", "instagram_rising", "tiktok_trends"):
        p = pathlib.Path(outdir) / f"rising_{ds}.json"
        if p.exists():
            out[ds] = json.load(open(p, encoding="utf-8"))
    return out
