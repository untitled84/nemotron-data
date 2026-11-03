# -*- coding: utf-8 -*-
"""composenemotron 2차 합성 — 니모트론 패널(panel.json) 위에 트렌드·웹·외부 실측·소셜 맥락을 얹는다. 정량 매칭 없음.

    import fusion as fu
    fused = fu.merge("<out>/panel.json", authored, meta_fusion)   # 융합층은 추가만 (원본 무변형)
    fu.verify(fused, "<out>/panel.json")                          # 실패 시 AssertionError
    fu.save(fused, "<out>")                                       # personas_fused.json + personas_fused.html

사실의 위계: 니모트론 원본 [Q] > 원본에서 유도 [Q-derived] > 트렌드·외부 실측 [T]/[X](집단) > [INF] 해석 > [가설].
정량 응답이 없으므로 브랜드 이력·카테고리 이용·SNS 이용은 개인 사실이 아니라 **[가설]** — FGD에서 흔들어 볼 대상이다.

meta_fusion = {"brand": "<브랜드 — 없으면 ''>", "category": "<카테고리 — 예: 커피>", "sources": [...], "conflicts_current": [...],
               "report_gap": "<fusion/trends/에 맞는 리포트가 정말 없을 때만 사유>"}

authored = {uuid: {
   "diary": ["1인칭 7~8줄"], "diary_trend_lines": [3, 6],          # 트렌드 유래 줄 2개+ (0부터)
   "trend_context": [{"tag": "[T:리포트]|[T:웹]", "fact", "source", "when", "url", "axis": "ⓐ|ⓑ|ⓒ|ⓓ", "key": "<[T:리포트]면 fusion/trends/ 파일명>"}],  # 3건+, 3축+
   "sns_use": {"platforms": ["유튜브", "인스타그램", ...], "tag": "[T:리포트]|[T:웹]|[가설]", "basis": "<연령대 이용률 통계 + 니모트론 서술 단서>"},
   "media_diet": "... (추정)",                                     # sns_use.platforms 중 1개+ 이름으로 언급 (비었으면 '미이용'을 적는다)
   "instagram": {"handle","bio","grid":[...],"style","follows":[...],"grounding":[{"tag":"[X:인스타]","from","value","used_for"}]},
   "rising_feed": [{"platform":"유튜브|인스타|틱톡","tag":"[X:유튜브·급상승]|...","item","match","level":"피드|들어봄","used_in"}],   # 풀 있으면 3~5
   "media_grounding": [{"tag":"[X:유튜브]","from","value"}],
   "common_ground": {"band":"20대","items":[{"item","level":"보편|다수|추정","stat":"..%","source","when","tag","url"}],"excluded":[...],"personal_override":[...]},
   "life_scenes": [{"area":"식생활|여가·취향|일|관계|동네·주거","text","body_fields":[...],"tag":"[Q]|[Q-derived]","quote":"<선택: 원문 일부>"}],  # 4영역+ · 건강 필드 금지
   "category_moments": [{"scene","text","body_fields":[...],"tag":"[Q]|[Q-derived]|[가설]|[Q-derived]+[가설]","quote":"<[Q]면 필수: 원문 일부>"}],  # 2~3
   "brand_relation": {"past","now","next","story","tag":"[가설]","trigger","trigger_tag":"[INF]","fgd_probe":"<FGD에서 이 가설을 흔들 질문>"},
   "category_meaning": {"role":"보상|연료|쉼|사교|절제|습관|탐험|관리|정체성|과시","line","basis":[니모트론 필드...]},
   "adjacent_consumption": [{"item","tag":"[Q]|[Q-derived]|[T:리포트]|[가설]","basis","key":"<[T:리포트]면 파일명>"}],   # 2건+
   "voice": {"habits":[...],"samples":[3문장],"basis":["big5", ...]},
   "external": [{"dataset":"time_use|naver_datalab|media_panel","tag":"[X:생활시간]|[X:데이터랩]|[X:미디어패널]","fact","cell","used_in","source","when"}],
   "audit": {"소스","4축","오염","충돌","계측"}}}
"""
import copy, html as _h, itertools, json, os, re, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

BANDS = [(0, 18, "10대"), (19, 29, "20대"), (30, 39, "30대"), (40, 49, "40대"), (50, 59, "50대"), (60, 200, "60대+")]
band_of = lambda a: next(n for lo, hi, n in BANDS if lo <= a <= hi)   # 니모트론 하한 19세 → 20대(19~29). 외부 실측 셀은 통계 원표 기준(external._band: 19세=10대)

USAGE_RULE_FUSION = (
    "fused는 정량 매칭 없는 2차 합성이다. 사실 근거는 raw(니모트론 원본 [Q])와 rows뿐이다. "
    "fused.trend_context·external·instagram.grounding·media_grounding·rising_feed는 집단·플랫폼 수준 맥락이다 — '요즘 내 또래는 ~라던데'는 정상, '그래서 나도 ~했다'는 위반. "
    "fused.brand_relation·sns_use([가설]일 때)·category_moments 중 [가설] 장면은 **검증되지 않은 가설**이다 — 말하되 모더레이터가 파고들면 흔들릴 수 있어야 하고, "
    "참여자가 '사실 잘 모르겠다'로 물러서는 것도 정상이다. 가설을 지키려고 이야기를 덧붙이지 마라. fgd_probe는 그 가설을 흔들 질문이다. "
    "fused.media_diet·instagram은 [추정] 프로젝션이다 — 실제로 그 계정을 운영한다고 말하지 마라. "
    "fused.common_ground가 발화의 하한선이다: 보편=당연히 앎, 다수=개인 신호 없으면 '아마', 추정='들어는 봤을 법', excluded=모를 수 있음. "
    "fused.life_scenes는 몸체 결합([Q]/[Q-derived])이라 자기 생활로 말해도 된다. fused.voice는 말투 가이드다(샘플 문장 반복 금지). "
    "데이터랩 ratio는 상대값이다."
)

HEALTH_FIELDS = {"bmi_status", "blood_pressure_status", "blood_sugar_status", "waist_status", "smoking_status",
                 "drinking_status", "healthcare_persona"}
LIFE_AREAS = {"식생활", "여가·취향", "일", "관계", "동네·주거"}
MEANING_ROLES = {"보상", "연료", "쉼", "사교", "절제", "습관", "탐험", "관리", "정체성", "과시"}
MOMENT_TAGS = {"[Q]", "[Q-derived]", "[가설]", "[Q-derived]+[가설]", "[Q]+[가설]"}
X_TAGS = {"time_use": "[X:생활시간]", "media_panel": "[X:미디어패널]", "naver_datalab": "[X:데이터랩]"}
ABS_VOLUME = re.compile(r"검색(량|수|건수)\s*[:은는이가]?\s*\d")
PERSONALIZE = re.compile(r"(그래서|덕분에|따라서|그 말 듣고)\s*나도|나도\s*(따라|그래서)")
PLATFORM_ALIASES = {"유튜브": ("유튜브", "YouTube", "쇼츠"), "인스타그램": ("인스타", "Instagram", "릴스"), "틱톡": ("틱톡", "TikTok"),
                    "블로그": ("블로그",), "페이스북": ("페이스북", "Facebook"), "X": ("X(", "트위터", "엑스"), "스레드": ("스레드", "Threads"),
                    "카카오스토리": ("카카오스토리",), "커뮤니티": ("커뮤니티", "디시", "더쿠", "네이트판", "인스티즈"), "네이버 카페": ("네이버 카페", "카페(네이버")}


def _pct(stat):
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(stat or ""))
    return float(m.group(1)) if m else None


def _age_in(age, label):
    nums = [int(x) for x in re.findall(r"\d+", str(label))]
    if not nums: return False
    if "+" in str(label): return age >= nums[0]
    if len(nums) == 1: return nums[0] <= age < nums[0] + 10
    return nums[0] <= age <= nums[1]


def _raw_text(raw):
    return " ".join(str(v) for v in raw.values() if isinstance(v, str))


def merge(panel_json, authored, meta_fusion):
    src = json.load(open(panel_json, encoding="utf-8"))
    out = copy.deepcopy(src)
    for s in out["segments"]:
        for p in s["personas"]:
            a = authored.get(p["uuid"])
            assert a, f"{p.get('name', p['uuid'])} 저작 블록 없음"
            p["fused"] = a
    meta = out.setdefault("meta", {})
    mf = dict(meta_fusion)
    mf["usage_rule"] = (meta.get("fusion", {}).get("usage_rule", "") + " " + USAGE_RULE_FUSION).strip()
    meta["fusion"] = {**meta.get("fusion", {}), **mf}
    return out


def verify(fused, panel_json, trends_dir=None):
    """보존 + 가설 규율 + 상식 기저 + 일기 + 트렌드 출처 + 미디어·인스타 정합 + 외부 실측 셀 + 소셜·급상승 실재 + 오염 계산.
    실패하면 AssertionError. 통과 라인 목록을 돌려준다(meta.fusion.preservation에도 기록)."""
    import trends as _tr, external as _x
    if trends_dir: os.environ["NEMO_TRENDS_DIR"] = str(trends_dir)
    tdir = _tr.trends_dir()
    tlib = {pathlib.Path(m["path"]).name: m for m in _tr.load()}
    x_avail = {k for k, v in _x.available().items() if v}
    outdir = os.path.dirname(os.path.abspath(panel_json))
    social = _x.load_social(outdir); rising = _x.load_rising(outdir)
    report_gap = (fused["meta"].get("fusion") or {}).get("report_gap")
    warn = []; n = n_rep = n_ig = n_yt = n_rf = 0; hyp_total = 0

    src_doc = json.load(open(panel_json, encoding="utf-8"))
    src = {p["uuid"]: p for s in src_doc["segments"] for p in s["personas"]}
    out = {p["uuid"]: p for s in fused["segments"] for p in s["personas"]}
    assert set(src) == set(out), "인물 누락/추가"
    for u, sp in src.items():
        for k in ("raw", "rows", "contradiction", "boundary", "title", "header", "name"):
            assert out[u].get(k) == sp.get(k), f"{out[u].get('name')} {k} 변형"
    lines = [f"✅ 보존 검증 통과: {len(src)}명 · raw(니모트론 원본)·rows·모순·경계·제목 무변형"]

    for p in out.values():
        F = p["fused"]; nm = p.get("name", p["uuid"][:8]); raw = p["raw"]; rtxt = _raw_text(raw)
        age = int(raw["age"])

        # ── SNS 이용 가설 (정량 없음 → 근거 태그 필수)
        su = F.get("sns_use") or {}
        plats = list(su.get("platforms") or [])
        assert su.get("tag") in ("[T:리포트]", "[T:웹]", "[가설]") and su.get("basis"), f"{nm} sns_use: tag([T:리포트]|[T:웹]|[가설])·basis 필요"
        for pl in plats:
            assert pl in PLATFORM_ALIASES, f"{nm} sns_use 플랫폼 '{pl}' — {sorted(PLATFORM_ALIASES)} 중에서"
        hyp_total += su["tag"] == "[가설]"

        # ── 상식 기저
        cg = F.get("common_ground") or {}
        assert cg.get("items"), f"{nm} common_ground 없음"
        assert cg.get("band") == band_of(age), f"{nm} 연령대 불일치({cg.get('band')} vs {band_of(age)})"
        po = json.dumps(cg.get("personal_override", []), ensure_ascii=False)
        for it in cg["items"]:
            item = str(it.get("item", "")); lv = it.get("level")
            assert it.get("source") and it.get("when") and lv in ("보편", "다수", "추정"), f"{nm} {item} 근거·등급 누락"
            pct = _pct(it.get("stat"))
            if lv in ("보편", "다수"):
                assert pct is not None, f"{nm} {item}: '{lv}'인데 stat에 % 없음"
                assert (pct >= 70) if lv == "보편" else (50 <= pct < 70), f"{nm} {item}: {pct}%인데 '{lv}' (보편≥70 · 다수 50~69)"
                for pl, al in PLATFORM_ALIASES.items():
                    if any(a in item for a in al) and pl not in plats:
                        assert any(a in po for a in al), f"{nm} sns_use에 없는 '{item}'={lv} — personal_override에 처리 근거를 적어라"

        # ── 트렌드 근거
        tc = F.get("trend_context", [])
        assert len(tc) >= 3, f"{nm} trend_context {len(tc)}건 (<3)"
        for t in tc:
            assert t.get("tag") in ("[T:리포트]", "[T:웹]") and t.get("source") and t.get("when"), f"{nm} 트렌드 태그·출처·시점 누락"
            if t["tag"] == "[T:리포트]":
                key = str(t.get("key", "")).replace("trends/", "")
                assert key and (tdir / key).exists(), f"{nm} [T:리포트] key '{key}'가 fusion/trends/에 없음"
                md = tlib.get(key)
                if md is not None:
                    assert _tr.fits_age(md, age) is not False, f"{nm}({age}세) — '{key}' 적용 연령({md.get('ages')}) 밖"
        assert len({t.get("axis") for t in tc if t.get("axis")}) >= 3, f"{nm} 4축 중 3축 미만"
        has_rep = any(t["tag"] == "[T:리포트]" for t in tc)
        assert has_rep or report_gap, f"{nm} [T:리포트] 0건 — fusion/trends/에서 찾거나 meta_fusion['report_gap']에 사유"
        n_rep += has_rep

        # ── 일기
        d = F.get("diary", [])
        assert 7 <= len(d) <= 8, f"{nm} 일기 {len(d)}줄 (7~8)"
        tl = F.get("diary_trend_lines", [])
        assert len(set(tl)) >= 2 and all(isinstance(i, int) and 0 <= i < len(d) for i in tl), f"{nm} diary_trend_lines 2개+ · 범위 안"
        for i, line in enumerate(d):
            assert not PERSONALIZE.search(line), f"{nm} 일기 {i}줄 트렌드 개인화('그래서 나도~'): {line[:40]}"
        for m_ in re.finditer(r"(?:내|제|나는|저는)\s*(?:나이\s*)?(\d{2})\s*(?:살|세)", " ".join(d)):
            assert int(m_.group(1)) == age, f"{nm} 일기 속 본인 나이 {m_.group(1)} ≠ 원본 {age}"

        # ── 미디어 식단 · 인스타
        md_txt = str(F.get("media_diet", "")).strip()
        assert len(md_txt) >= 20, f"{nm} media_diet 비었거나 짧음"
        if plats:
            assert any(a in md_txt for pl in plats for a in PLATFORM_ALIASES[pl]), f"{nm} media_diet가 sns_use 플랫폼({plats}) 중 하나도 언급 안 함"
        else:
            assert any(k in md_txt for k in ("미이용", "안 쓴", "안 한", "쓰지 않", "하지 않")), f"{nm} sns_use 비었는데 media_diet에 미이용 언급 없음"
        ig = F.get("instagram", {})
        assert ig.get("style"), f"{nm} 인스타 style 없음"
        if "인스타그램" not in plats:
            assert any(k in ig["style"] for k in ("계정 없음", "눈팅", "비공개")), f"{nm} sns_use에 인스타그램 없음 — style은 계정 없음/눈팅/비공개 부계"

        # ── 몸체 결합 층
        def _fields_ok(fs, what):
            assert fs, f"{nm} {what}: body_fields 없음"
            for f_ in fs:
                assert f_ in raw, f"{nm} {what}: 원본에 없는 필드 '{f_}'"
                assert f_ not in HEALTH_FIELDS, f"{nm} {what}: 건강 필드 '{f_}'는 쓰지 않는다"
        def _quote_ok(q, what):
            q = str(q or "").strip()
            assert len(q) >= 6 and q in rtxt, f"{nm} {what}: quote가 원본 서술에 없음 — '{q[:30]}'"
        cited = set()
        ls = F.get("life_scenes", [])
        assert len({x.get("area") for x in ls} & LIFE_AREAS) >= 4, f"{nm} life_scenes 4영역 미만 ({sorted(LIFE_AREAS)})"
        for x in ls:
            assert len(str(x.get("text", ""))) >= 15 and x.get("tag") in ("[Q]", "[Q-derived]"), f"{nm} life_scenes '{x.get('area')}' 본문·태그([Q]|[Q-derived])"
            _fields_ok(x.get("body_fields"), f"life_scenes·{x.get('area')}"); cited |= set(x["body_fields"])
            if x.get("quote"): _quote_ok(x["quote"], f"life_scenes·{x.get('area')}")
        cm = F.get("category_moments", [])
        assert 2 <= len(cm) <= 3, f"{nm} category_moments {len(cm)}장면 (2~3)"
        for x in cm:
            tg = x.get("tag")
            assert tg in MOMENT_TAGS, f"{nm} category_moments '{x.get('scene')}' 태그 {tg} — {sorted(MOMENT_TAGS)}"
            _fields_ok(x.get("body_fields"), "category_moments"); cited |= set(x["body_fields"])
            if tg.startswith("[Q]"): _quote_ok(x.get("quote"), f"category_moments '{x.get('scene')}'([Q]는 원문 인용 필수)")
            hyp_total += "[가설]" in tg
        br = F.get("brand_relation") or {}
        assert br.get("tag") == "[가설]", f"{nm} brand_relation.tag는 '[가설]' — 정량 없이 브랜드 이력은 사실이 아니다"
        assert all(br.get(k) for k in ("past", "now", "next")) and len(str(br.get("story", ""))) >= 30, f"{nm} brand_relation past·now·next·story(30자+)"
        assert br.get("trigger") and br.get("trigger_tag") == "[INF]", f"{nm} brand_relation trigger([INF])"
        assert len(str(br.get("fgd_probe", ""))) >= 8, f"{nm} brand_relation.fgd_probe — 이 가설을 FGD에서 흔들 질문"
        hyp_total += 1
        mn = F.get("category_meaning") or {}
        assert mn.get("role") in MEANING_ROLES and mn.get("line") and mn.get("basis"), f"{nm} category_meaning role({sorted(MEANING_ROLES)})·line·basis"
        cited |= {b for b in mn["basis"] if b in raw}
        ac = F.get("adjacent_consumption", [])
        assert len(ac) >= 2, f"{nm} adjacent_consumption {len(ac)}건 (<2)"
        for x in ac:
            assert x.get("tag") in ("[Q]", "[Q-derived]", "[T:리포트]", "[가설]") and x.get("basis"), f"{nm} adjacent_consumption 태그·근거: {x.get('item')}"
            if x["tag"] == "[T:리포트]":
                key = str(x.get("key", "")).replace("trends/", "")
                assert key and (tdir / key).exists(), f"{nm} adjacent_consumption [T:리포트] key '{key}' 없음"
            hyp_total += x["tag"] == "[가설]"
        vc = F.get("voice") or {}
        assert len(vc.get("samples", [])) == 3 and vc.get("habits") and vc.get("basis"), f"{nm} voice habits·basis + 샘플 3문장"

        # ── 외부 실측 (니모트론 셀)
        xs = F.get("external", [])
        cell = _x.cell_of(p)
        ok_cells = {"전 국민"} | {"×".join(str(cell[k]) for k in combo) for r in range(1, 5)
                                 for combo in itertools.combinations(_x.CELL_KEYS, r) if all(cell.get(k) for k in combo)}
        for x in xs:
            ds = x.get("dataset")
            assert ds in X_TAGS and x.get("tag") == X_TAGS[ds], f"{nm} external 데이터셋·태그 불일치: {ds} {x.get('tag')}"
            assert ds in x_avail, f"{nm} external '{ds}' — fusion/external/에 집계표가 없는데 인용"
            assert x.get("fact") and x.get("source") and x.get("when") and x.get("used_in"), f"{nm} external {ds}: fact·source·when·used_in"
            assert str(x.get("cell", "")) in ok_cells, f"{nm} external {ds}: cell '{x.get('cell')}'가 이 사람 셀과 다름 (가능: {sorted(ok_cells)})"
            if ds == "naver_datalab":
                assert not ABS_VOLUME.search(x["fact"]), f"{nm} 데이터랩 ratio는 상대값: {x['fact'][:40]}"
        assert any(x.get("dataset") == "time_use" for x in xs) or "time_use" not in x_avail, f"{nm} [X:생활시간] 1건+ (집계표가 있다)"
        if "naver_datalab" in x_avail and not any(x.get("dataset") == "naver_datalab" for x in xs):
            warn.append(f"{nm} [X:데이터랩] 미사용(기본 파일 키워드가 카테고리와 다르면 정상)")

        # ── 소셜 실측
        igg = ig.get("grounding", []); mg = F.get("media_grounding", [])
        for g in igg + mg:
            assert g.get("tag") in ("[X:인스타]", "[X:유튜브]") and g.get("from") and g.get("value"), f"{nm} 소셜 근거 tag·from·value"
            ds = "instagram" if g["tag"] == "[X:인스타]" else "youtube"
            assert ds in social, f"{nm} {g['tag']} 인용 — 이 실행에 social_{ds}.json 없음"
            assert str(g["value"]).lstrip("#") in json.dumps(social[ds], ensure_ascii=False), f"{nm} {g['tag']} 값 '{g['value']}'이 수집 요약에 없음"
        if "instagram" in social and "인스타그램" in plats:
            assert sum(g.get("tag") == "[X:인스타]" for g in igg) >= 2, f"{nm} 인스타 이용(가설) — 프로젝션 근거 [X:인스타] 2건+"
            n_ig += 1
        if "youtube" in social and "유튜브" in plats:
            assert any(g.get("tag") == "[X:유튜브]" for g in mg), f"{nm} 유튜브 이용(가설) — media_grounding [X:유튜브] 1건+"
            n_yt += 1

        # ── 떠오르는 콘텐츠
        rf = F.get("rising_feed", [])
        if rising:
            assert 3 <= len(rf) <= 5, f"{nm} rising_feed {len(rf)}건 (3~5)"
            interests = _x.interest_terms(p)
            for r in rf:
                ds = _x.RISING_TAGS.get(r.get("tag"))
                assert ds and ds in rising, f"{nm} rising_feed 태그 '{r.get('tag')}' — 이 실행에 그 풀 없음"
                assert r.get("platform") in _x.PLATFORM_SNS and r.get("item") and r.get("match") and r.get("used_in"), f"{nm} rising_feed platform·item·match·used_in"
                assert str(r["item"]).lstrip("#") in json.dumps(rising[ds], ensure_ascii=False), f"{nm} rising_feed '{r['item']}' 풀에 없음"
                assert r["match"] in interests, f"{nm} rising_feed 매칭어 '{r['match']}'가 니모트론 취미·식생활·여가 서술에 없음"
                if _x.PLATFORM_SNS[r["platform"]] not in plats:
                    assert r.get("level") == "들어봄", f"{nm} sns_use에 {r['platform']} 없음 — '{r['item']}'은 level='들어봄'"
                if ds == "tiktok_trends":
                    hit = next((h for h in rising[ds]["hashtags"] if h["hashtag"] == str(r["item"]).lstrip("#")), None)
                    if hit and hit.get("audience_ages") and not any(_age_in(age, a) for a in hit["audience_ages"]):
                        warn.append(f"{nm}({age}세) 틱톡 '{r['item']}' 주 시청 연령 밖")
            n_rf += 1

        # ── 감사 + 오염 계산
        assert F.get("audit") and all(k in F["audit"] for k in ("소스", "4축", "오염", "충돌", "계측")), f"{nm} AUDIT 5줄 누락"
        t_n = len(tc) + len(set(tl)) + sum(x["tag"] == "[T:리포트]" for x in ac) + len(xs) + len(igg) + len(mg) + len(rf) + (su["tag"] != "[가설]")
        inf_n = len(ig.get("grid", [])) + 3                              # 계기 · 의미 · 말투
        hyp_n = 3 + sum("[가설]" in x.get("tag", "") for x in cm) + sum(x["tag"] == "[가설]" for x in ac) + (su["tag"] == "[가설]")
        anchor_n = len(p["rows"]) + len(cited)
        F["audit_computed"] = {"[T]+[X]": t_n, "[INF]": inf_n, "[가설]": hyp_n, "앵커([Q] rows+인용 필드)": anchor_n,
                               "비율": round((t_n + inf_n + hyp_n) / max(anchor_n, 1), 2)}
        assert inf_n + hyp_n <= anchor_n, f"{nm} 해석·가설({inf_n + hyp_n})이 사실 앵커({anchor_n})보다 큼 — body_fields 근거를 늘리거나 가설을 줄여라"
        assert t_n + inf_n + hyp_n <= 2 * anchor_n, f"{nm} 2차층({t_n + inf_n + hyp_n})이 앵커의 2배({2 * anchor_n}) 초과 — 융합이 원본을 덮는다"
        n += 1

    for s in fused["segments"]:
        seen = {}
        for p in s["personas"]:
            ig = p["fused"].get("instagram", {}); g = tuple(ig.get("grid", []))
            if not g: continue
            for nm2, (st2, g2) in seen.items():
                assert g != g2, f"{s.get('title') or s['name']}: {p['name']}·{nm2} 인스타 grid 동일"
                assert not (ig.get("style") == st2 and len(set(g) & set(g2)) >= max(2, len(g) // 2)), f"{s.get('title') or s['name']}: {p['name']}·{nm2} 인스타 style 같고 grid 절반+ 겹침"
            seen[p["name"]] = (ig.get("style"), g)

    lines.append(f"✅ 가설 규율: {n}명 · 브랜드 관계 전원 [가설]+FGD 검증 질문 · [가설] 층 총 {hyp_total}건 · SNS 이용 근거 태그")
    lines.append(f"✅ 상식 기저: 연령대(원본 나이) 일치 · 등급↔수치 일치 · SNS 가설과 충돌 시 override")
    lines.append(f"✅ 융합 기준: 트렌드 3건+·3축+ (리포트 사용 {n_rep}명{'' if n_rep == n else ' · report_gap: ' + str(report_gap)}) · 리포트 연령 적합 · "
                 f"일기 7~8줄(트렌드 2줄+·개인화 없음) · 미디어·인스타 SNS 가설 정합 · 세그 내 인스타 중복 없음 · 오염(해석+가설 ≤ 앵커, 2차층 ≤ 앵커×2)")
    lines.append("✅ 외부 실측: " + (" · ".join(X_TAGS[d] for d in sorted(x_avail)) if x_avail else "집계표 없음") + " · 셀 = 니모트론 성×연령대(+취업·가구)")
    lines.append("✅ 소셜 실측: " + (" · ".join(f"{k} 요약" for k in social) if social else "이 실행에 수집 없음")
                 + (f" · 인스타 이용 가설 {n_ig}명 근거 2건+" if "instagram" in social else "") + (f" · 유튜브 {n_yt}명" if "youtube" in social else ""))
    lines.append("✅ 떠오르는 콘텐츠: " + (f"풀 {', '.join(sorted(rising))} · {n_rf}명 3~5건 · 관심사 매칭·풀 실재" if rising else "이 실행에 수집 없음"))
    lines.append(f"✅ 몸체 결합: {n}명 · 생활 장면 4영역+(건강 필드 없음) · 카테고리 장면 2~3([Q]는 원문 인용 실재) · 의미 · 인접 소비 2+ · 말투 3")
    if warn:
        lines.append("ℹ️ 참고(실패 아님): " + " · ".join(warn[:8]) + (f" 외 {len(warn) - 8}건" if len(warn) > 8 else ""))
    fused["meta"]["fusion"]["preservation"] = " / ".join(lines)
    return lines


def _e(x): return _h.escape(str(x))


def _ga(w):
    """받침 따라 '이'/'가' — 커피가 · 화장품이."""
    c = str(w or "")[-1:]
    return (w + ("이" if (ord(c) - 0xAC00) % 28 else "가")) if c and 0xAC00 <= ord(c) <= 0xD7A3 else f"{w}이(가)"


def render_html(fused, path):
    M = fused.get("meta", {}); FU = M.get("fusion", {})
    cat = FU.get("category") or "카테고리"; brand = FU.get("brand") or ""
    secs = ""; probes_all = []
    for s in fused["segments"]:
        cards = ""
        for p in s["personas"]:
            F = p["fused"]; ig = F.get("instagram", {}); cg = F.get("common_ground", {}); su = F.get("sns_use", {})
            br = F.get("brand_relation", {}); mn = F.get("category_meaning", {}); vc = F.get("voice", {})
            if br.get("fgd_probe"): probes_all.append((p.get("name", ""), s.get("title") or s.get("name", ""), br["fgd_probe"]))
            diary = "".join(f'<p class="{"tr" if i in F.get("diary_trend_lines", []) else ""}">{_e(l)}</p>' for i, l in enumerate(F["diary"]))
            tc = "".join(f'<li><span class="tg t">{_e(t["tag"])}</span> {_e(t["fact"])} <span class="src">— {_e(t["source"])}, {_e(t["when"])}</span></li>' for t in F["trend_context"])
            cgi = "".join(f'<li><b>{_e(i["level"])}</b> {_e(i["item"])} <span class="src">{_e(i.get("stat",""))} · {_e(i["source"])} {_e(i["when"])}</span></li>' for i in cg.get("items", []))
            cgx = "".join(f'<li>제외 · {_e(i["item"])} <span class="src">{_e(i.get("reason",""))}</span></li>' for i in cg.get("excluded", []))
            ls_h = "".join(f'<li><b>{_e(x.get("area",""))}</b> {_e(x.get("text",""))} <span class="tg q">{_e(x.get("tag",""))}</span></li>' for x in F.get("life_scenes", []))
            cm_h = "".join(f'<li><b>{_e(x.get("scene",""))}</b> {_e(x.get("text",""))} <span class="tg {"h" if "가설" in x.get("tag","") else "q"}">{_e(x.get("tag",""))}</span></li>' for x in F.get("category_moments", []))
            ac_h = "".join(f'<li><span class="tg {"h" if x.get("tag")=="[가설]" else "t"}">{_e(x.get("tag",""))}</span> {_e(x.get("item",""))} <span class="src">{_e(x.get("basis",""))}</span></li>' for x in F.get("adjacent_consumption", []))
            xs_h = "".join(f'<li><span class="tg t">{_e(x.get("tag",""))}</span> {_e(x.get("fact",""))} <span class="src">셀 {_e(x.get("cell",""))} · {_e(x.get("source",""))} {_e(x.get("when",""))} → {_e(x.get("used_in",""))}</span></li>' for x in F.get("external", []))
            rf_h = "".join(f'<li><span class="tg t">{_e(r.get("tag",""))}</span> {_e(r.get("item",""))} <span class="src">{_e(r.get("level",""))} · 관심사 {_e(r.get("match",""))} → {_e(r.get("used_in",""))}</span></li>' for r in F.get("rising_feed", []))
            rows = "".join(f'<li><b>{_e(r[0])}</b> {_e(r[1])} <span class="tg q">{_e(r[2]) if len(r) > 2 else ""}</span></li>' for r in p["rows"])
            raw_n = "".join(f'<li>{_e(k)}: {_e(v)}</li>' for k, v in p["raw"].items())
            au = "".join(f'<li><b>{_e(k)}</b> {_e(v)}</li>' for k, v in F.get("audit", {}).items())
            au += "".join(f'<li><b>계산 · {_e(k)}</b> {_e(v)}</li>' for k, v in F.get("audit_computed", {}).items())
            cards += f'''<div class="c"><div class="hd">{_e(p.get("title",""))}</div><div class="hs">{_e(p["header"])}</div>
<div class="diary">{diary}</div>
<h4>{_e(_ga(cat))} 놓이는 장면</h4><ul>{cm_h}</ul>
<h4>브랜드 관계 <span class="tg h">가설</span></h4><p class="sm"><b>{_e(br.get("past",""))} → {_e(br.get("now",""))} → {_e(br.get("next",""))}</b><br>{_e(br.get("story",""))}<br><span class="src">계기 {_e(br.get("trigger",""))}</span> <span class="tg i">INF</span><br><span class="probe">FGD 검증 · {_e(br.get("fgd_probe",""))}</span></p>
<h4>{_e(cat)}의 의미 <span class="tg i">INF</span></h4><p class="sm"><b>{_e(mn.get("role",""))}</b> — {_e(mn.get("line",""))}</p>
<h4>{_e(cat)} 밖 소비</h4><ul>{ac_h}</ul>
{('<h4>요즘 피드에 뜨는 것 <span class="tg t">X·급상승</span></h4><ul>' + rf_h + '</ul>') if rf_h else ''}
<h4>미디어 식단 <span class="tg i">추정</span></h4><p class="sm">{_e(F.get("media_diet",""))}</p><div class="src">SNS 이용 {_e(su.get("tag",""))}: {_e(", ".join(su.get("platforms", [])) or "미이용")} — {_e(su.get("basis",""))}</div>{"".join(f'<div class="src"><span class="tg t">{_e(g.get("tag",""))}</span> {_e(g.get("from",""))}: {_e(g.get("value",""))}</div>' for g in F.get("media_grounding", []))}
<h4>인스타그램 프로젝션 <span class="tg i">INF·추정</span></h4><div class="ig"><b>{_e(ig.get("handle",""))}</b> · {_e(ig.get("style",""))}<br>{_e(ig.get("bio",""))}
<ul>{"".join(f"<li>{_e(g)}</li>" for g in ig.get("grid", []))}</ul><span class="src">팔로우: {_e(", ".join(ig.get("follows", [])))}</span>
{"".join(f'<div class="src"><span class="tg t">{_e(g.get("tag",""))}</span> {_e(g.get("from",""))}: {_e(g.get("value",""))} → {_e(g.get("used_for",""))}</div>' for g in ig.get("grounding", []))}</div>
<details class="fold"><summary>생활 장면 · Q·몸체</summary><ul>{ls_h}</ul></details>
<details class="fold"><summary>트렌드 근거 {len(F.get("trend_context", []))}건</summary><ul>{tc}</ul></details>
{('<details class="fold"><summary>룩어라이크 외부 실측 · X·집단</summary><ul>' + xs_h + '</ul></details>') if xs_h else ''}
<details class="fold"><summary>말투 · 추정</summary><p class="sm">{_e(" · ".join(vc.get("habits", [])))}</p><ul>{"".join(f"<li>“{_e(x)}”</li>" for x in vc.get("samples", []))}</ul></details>
<details class="fold"><summary>상식 기저 ({_e(cg.get("band",""))} 근거)</summary><ul>{cgi}{cgx}</ul></details>
<details><summary>1차 앵커 — 합성 축 {len(p["rows"])}행</summary><ul>{rows}</ul><p class="src">모순: {_e(p.get("contradiction",""))}<br>경계: {_e(p.get("boundary",""))}</p></details>
<details><summary>원본 전체 데이터 — 니모트론 {len(p["raw"])}필드 · 전부 보존됨</summary><ul class="raw">{raw_n}</ul></details>
<details><summary>감사 로그</summary><ul>{au}</ul></details></div>'''
        secs += (f'<section><div class="band" style="background:{s.get("color","#444")}"><h2>{_e(s.get("title") or s["name"])}</h2>'
                 f'<span class="cr">{_e(s.get("subtitle") or s["name"])}</span></div><div class="grid">{cards}</div></section>')
    conf = "".join(f'<li><b>{_e(c.get("title",""))}</b> {_e(c.get("body",""))}</li>' for c in FU.get("conflicts_current", []))
    srcs = "".join(f'<li>{_e(x)}</li>' for x in (FU.get("sources") or []))
    probes = "".join(f'<li><b>{_e(a)}</b> <span class="src">{_e(b)}</span> — {_e(c)}</li>' for a, b, c in probes_all)
    title = M.get("title") or f"{brand or cat} 패널"
    doc = f'''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)} · 2차 합성</title><style>
:root{{--bg:#f5f6f8;--card:#fff;--ink:#1c2230;--sub:#5b6472;--line:#e4e7ec}}*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;line-height:1.5;padding:26px 16px 60px}}
.wrap{{max-width:1180px;margin:0 auto}}h1{{font-size:23px;margin:0 0 6px}}.note{{background:#eef7f1;border:1px solid #cfe6d8;border-radius:10px;padding:11px 15px;font-size:12.5px;color:#28553f;margin:12px 0 20px}}
section{{margin-bottom:26px}}.band{{display:flex;flex-direction:column;gap:2px;padding:10px 14px;border-radius:9px;color:#fff;margin-bottom:12px}}.band h2{{margin:0;font-size:15.5px}}.band .cr{{font-size:12px;opacity:.93}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}}@media(max-width:860px){{.grid{{grid-template-columns:1fr}}}}
.c{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 14px;font-size:12px}}
.hd{{font-size:14.5px;font-weight:700;line-height:1.35}}.hs{{font-size:11.5px;color:var(--sub);margin:2px 0 8px;padding-bottom:7px;border-bottom:1px solid var(--line)}}
.diary p{{margin:0 0 3px}}.diary p.tr{{color:#2b5d9e}}h4{{font-size:11.5px;color:var(--sub);margin:10px 0 3px}}ul{{margin:0;padding-left:16px}}li{{margin:2px 0}}
.src{{color:#8a929d;font-size:10.5px}}.probe{{color:#9a5b00;font-size:10.5px}}.tg{{display:inline-block;font-size:10px;padding:0 6px;border-radius:10px}}.tg.t{{background:#e9f0fb;color:#2b5d9e}}.tg.i{{background:#f3ecfb;color:#5b3fa0}}.tg.q{{background:#e6f4ee;color:#1f6f5c}}.tg.h{{background:#fdf1e1;color:#9a5b00}}
.ig{{background:#faf7fd;border:1px dashed #d9cdee;border-radius:8px;padding:7px 9px}}.sm{{margin:0}}details{{margin-top:7px}}summary{{cursor:pointer;color:var(--sub);font-size:11px}}details.fold>summary{{font-size:12.5px;font-weight:600;color:var(--ink);padding:5px 0;border-top:1px solid var(--line)}}details.fold[open]>summary{{margin-bottom:4px}}.raw{{max-height:220px;overflow:auto;font-size:10.5px}}
</style></head><body><div class="wrap"><h1>{_e(title)} · 2차 합성</h1>
<div class="note">정량 매칭 없음 — 사실 근거는 니모트론 원본 [Q]뿐 · 주황 태그 = [가설](FGD에서 검증) · 일기 파란 줄 = 트렌드 유래(배경) · 트렌드·미디어·인스타는 개인 사실이 아니다<br>{_e(FU.get("preservation",""))}</div>
{secs}<section><h3>FGD에서 검증할 가설</h3><ul>{probes}</ul><h3>충돌 로그</h3><ul>{conf}</ul><h3>2차 소스 (게이트 통과)</h3><ul>{srcs}</ul></section></div></body></html>'''
    open(path, "w", encoding="utf-8").write(doc)
    return path


def save(fused, outdir):
    json.dump(fused, open(os.path.join(outdir, "personas_fused.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    render_html(fused, os.path.join(outdir, "personas_fused.html"))
    return outdir
