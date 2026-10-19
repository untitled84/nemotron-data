# -*- coding: utf-8 -*-
r"""2단계 '신호 실재 검색' 헬퍼 — 합성 전에 데이터에 신호가 진짜 있는지 확인한다.

키워드별 풀 규모(+니모트론 100만 내 환산 — 한국 인구 추정치가 아니다) + (선택) 교집합 + 무작위 문맥 샘플을 출력한다.
키워드가 references/calibration.json의 축에 해당하면 외부 통계 대비 보정 행을 함께 찍는다.

오탐은 두 종류다 — 둘을 섞으면 못 잡는다:
  (a) 문자열 오탐 — 다른 단어에 부분 매칭. '라이브'는 '드라이브'에 걸린다.
      → --exclude-prefix 로 앞글자 배제.
  (b) 의미 오탐 — 단어는 맞는데 지시 대상이 다르다. **이게 더 위험하다.**
      '쇼핑'(6.1%)은 대부분 백화점·아울렛 **오프라인**이었고, '네이버'(2.63%)는
      블로그·웹툰·지도라 **네이버쇼핑이 아니었다**. 배제 규칙으로는 원리적으로 못 잡는다.
      → 문맥 샘플을 눈으로 보고 **과녁 비율**을 세서 카운트를 보정한다.
        ("쇼핑 850명, 그중 온라인 맥락 2/10 → 유효 풀 ~170명")
        과녁 비율이 30% 미만이면 그 키워드는 버리고 더 좁은 표현으로 다시 스캔한다.

부재 선언 주의 — 이 스크립트의 기본 스캔은 서술형 13개 중 3개뿐이다:
  "신호가 없다"는 이 스킬의 방어선이자 세그 설계를 통째로 바꾸는 판정인데,
  그 판정을 3/13 컬럼 위에서 내리면 부재가 **스캔 범위의 아티팩트**일 수 있다.
  AI 활용은 professional_persona에, 돈·가격 행동은 finance_persona에 산다.
  → 신호가 1% 미만이거나 '부재'를 선언하려면 반드시 --deep 으로 다시 돌려라.
    (rg 1개면 확장해도 몇 초다. 부재 선언 시 근거 컬럼 목록을 게이트 A에 병기할 것.)

사용:
  python3 signal_scan.py gh --kw 아이돌 --age 19 29          # 로컬 원본 없이(원격)
  python3 signal_scan.py /path/nemotron.parquet --kw 아이돌 뉴진스 --kw2 게임 스팀 --age 19 29
  python3 signal_scan.py <parquet> --kw AI 인공지능 --deep      # 부재 의심 시 서술형 확장
  python3 signal_scan.py <parquet> --kw 라이브 --exclude-prefix 라이브=드   # '드라이브' 배제
  --kw / --kw2  1차·2차 신호군 → 교집합 자동 계산
  --rg          row group 인덱스(기본 0). 인구정렬이라 1~2개면 비율 추정에 충분.
  --cols        스캔 컬럼 직접 지정
  --samples     문맥 샘플 수(기본 10, 무작위 추출)
  --re / --re2  정규식 신호군(키워드 대신·함께). references/net_patterns.md 의 그물을 그대로 넣는다.
  --neg         매칭 전에 텍스트에서 지울 정규식(비유·금융 문맥 제외 등). 모든 신호군에 적용.
  --body        수면·통증 같은 신체 서사는 신체·일상 컬럼에서만 찾는다(finance_persona 제외).
  예) python3 signal_scan.py gh --age 30 69 --deep \
        --re "불면|밤잠|잠을 설|숙면|뒤척" --neg "(밤잠을 설칠|잠을 설칠)\s*(정도|만큼)" --body \
        --re2 "IT 기기|가젯|테크|태블릿|스마트워치|명상 음악|ASMR|팟캐스트|앱으로|앱을"
      ('앱'·'유튜브' 단독은 30~69세의 절반 이상에 걸린다 — 기기 성향 신호가 아니다)
"""
import argparse, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nemotron_reader import NemotronParquet
from nemotron_remote import open_nemotron   # 로컬 원본이 없으면 GitHub에서 필요한 구간만 받는다

# 기본 — 싸고 신호 밀도가 높은 3개
TEXT_COLS = ["hobbies_and_interests_list", "arts_persona", "persona"]
# --deep — 부재를 선언하려면 여기까지 봐야 한다. 삶이 통째로 들어 있는 필드들.
DEEP_COLS = TEXT_COLS + ["detailed_persona", "professional_persona", "finance_persona",
                         "healthcare_persona", "family_persona", "hobbies_and_interests",
                         "skills_and_expertise", "career_goals_and_ambitions"]


def build_matcher(kw, excl):
    """매칭 위치를 돌려준다 (없으면 -1).

    예전엔 bool만 돌려주고, 문맥 출력은 따로 `t.find(kw)`를 썼다. 그래서
    **매처가 오탐이라 배제한 바로 그 자리**를 샘플로 보여주는 자기모순이 있었다.
    (예: '드라이브'의 '라이브'를 배제해 매칭시켜 놓고, 문맥은 '드라이브' 자리를 출력.)
    """
    bad = excl.get(kw, [])

    def m(t):
        i = 0
        while True:
            i = t.find(kw, i)
            if i < 0:
                return -1
            if i == 0 or t[i - 1] not in bad:
                return i
            i += 1
    return m


def _print_calibration(kws, age):
    """키워드가 보정표의 축에 해당하면 외부 통계 대비 비율을 찍는다.
    환산 수치는 니모트론 내부 수치다 — 외부와 얼마나 다른지 같이 보여줘야 사용자가 N과 '부재'를 제대로 판단한다."""
    import json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "calibration.json")
    if not os.path.exists(path):
        return
    try:
        calib = json.load(open(path, encoding="utf-8"))
    except Exception:
        return
    coh = None
    if age:
        lo, hi = age
        for c in ("19-29", "30-39", "40-49", "50-59", "60+"):
            a_, b_ = (int(c.split("-")[0]), int(c.split("-")[1])) if "-" in c else (60, 200)
            if lo >= a_ and hi <= b_:
                coh = c
    hits = []
    for ax, v in calib.get("axes", {}).items():
        if any(k in kw or kw in k for kw in kws for k in v["keywords"]) or any(kw in ax for kw in kws):
            hits.append((ax, v))
    if not hits:
        return
    print("\n  [보정표 references/calibration.md]")
    for ax, v in hits:
        rows = {r["cohort"]: r for r in v["rows"]}
        r = rows.get(coh) if coh else None
        r = r if (r and r["external_pct"] is not None) else rows.get("전체")
        if r["external_pct"] is None:
            print(f"  · 축 '{ax}' — 니모트론 언급률 {r['nemotron_pct']}% ({r['cohort']}) · 외부 통계 미확인 → 환산 수치를 한국 규모로 읽지 마라")
            continue
        flag = "니모트론이 적게 잡는 축 — 실제 풀은 이보다 크다. '부재' 선언 금지" if r["ratio"] < 0.5 else \
               "니모트론이 많이 잡는 축 — N은 보수적으로" if r["ratio"] > 1.5 else "근사 — 환산을 그대로 써도 큰 오차 없음"
        print(f"  · 축 '{ax}' ({r['cohort']}) — 니모트론 {r['nemotron_pct']}% vs 외부 {r['external_pct']}% "
              f"({r['external_def']} · {r['external_src']}) → 비율 {r['ratio']} · {flag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parquet")
    ap.add_argument("--kw", nargs="+", default=[])
    ap.add_argument("--kw2", nargs="+", default=[])
    ap.add_argument("--age", nargs=2, type=int, default=None)
    ap.add_argument("--rg", nargs="+", type=int, default=[0])
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--exclude-prefix", nargs="*", default=[])
    ap.add_argument("--deep", action="store_true",
                    help="서술형까지 확장 스캔 — 신호 <1%거나 부재 선언 시 필수")
    ap.add_argument("--cols", nargs="+", default=None, help="스캔 컬럼 직접 지정")
    ap.add_argument("--seed", type=int, default=0, help="샘플 재현용")
    ap.add_argument("--re", nargs="*", default=[], help="1차 정규식 신호군")
    ap.add_argument("--re2", nargs="*", default=[], help="2차 정규식 신호군")
    ap.add_argument("--neg", nargs="*", default=[], help="매칭 전 텍스트에서 지울 정규식")
    ap.add_argument("--body", action="store_true", help="신체·일상 컬럼만(finance 제외)")
    a = ap.parse_args()

    cols = a.cols or (DEEP_COLS if a.deep else TEXT_COLS)
    if a.body:
        cols = [c for c in cols if c != "finance_persona"] or ["healthcare_persona", "detailed_persona"]
    excl = {}
    for e in a.exclude_prefix:
        k, v = e.split("=", 1)
        excl[k] = list(v.replace(",", ""))

    npq = open_nemotron(a.parquet)            # a.parquet == 'gh' 이면 원격
    rows = npq.load(["age", "sex"] + cols, rg_indices=a.rg)
    scanned = len(rows)
    if a.age:
        rows = [r for r in rows if r["age"] and a.age[0] <= r["age"] <= a.age[1]]
    negs = [re.compile(x) for x in a.neg]
    def _clean(t):
        for g in negs:
            t = g.sub(" ", t)
        return t
    T = [(r, _clean(" ".join((r[c] or "") for c in cols))) for r in rows]
    n = len(T)
    if not n:
        print("모집단 0명 — 조건을 넓혀라"); return

    # 100만 환산 — rg 1개는 전체의 1.4%다. '41명'이 아니라 '41명 → 약 2,900명'이라
    # 말해야 사용자가 N을 정할 수 있다. 규칙이 사람 기억에만 있으면 빠지니 여기서 찍는다.
    total = npq.num_rows
    scale = total / scanned                     # 스캔 행 → 전체
    pool_est = round(n * scale)
    print(f"모집단: {n:,}명 (rg={a.rg}, {scanned:,}행 스캔"
          + (f", age {a.age[0]}~{a.age[1]}" if a.age else "") + ")")
    print(f"  → 니모트론 {total:,}행 내 환산 ≈ {pool_est:,}명 (스캔 비율 {scanned/total*100:.1f}%) — 한국 인구 추정치가 아니다")
    _print_calibration(a.kw + a.kw2, a.age)
    print(f"  스캔 컬럼 {len(cols)}개: {', '.join(cols)}")
    if not a.deep and not a.cols:
        print("  ⚠ 기본 3컬럼 스캔이다. 신호가 1% 미만이거나 '부재'를 선언하려면 --deep 으로 다시 돌려라.")
    print()

    def matcher(k):
        if k.startswith("re:"):
            g = re.compile(k[3:])
            def m(t):
                x = g.search(t)
                return x.start() if x else -1
            return m
        return build_matcher(k, excl)

    def scan(kws, label):
        hit = set()
        print(f"=== {label} ===")
        print(f"  {'키워드':<14}{'표본':>7}{'비율':>8}{'니모트론 환산':>12}")
        for k in kws:
            m = matcher(k)
            idx = [i for i, (r, t) in enumerate(T) if m(t) >= 0]
            est = round(len(idx) * scale)
            flag = ""
            if len(idx) == 0:
                flag = "  ← 신호 없음. 이 축으론 세그 못 세움"
            elif len(idx) / n < 0.01:
                flag = "  ← 1% 미만. --deep 으로 재확인 전엔 부재 선언 금지"
            print(f"  {k:<14}{len(idx):>7,}{len(idx)/n*100:>7.2f}%{est:>11,}명{flag}")
            hit |= set(idx)
        if kws:
            print(f"  → 합집합(중복 제거): {len(hit):,}명 ({len(hit)/n*100:.2f}%) → 니모트론 환산 ≈ {round(len(hit)*scale):,}명\n")
        return hit

    k1 = a.kw + ["re:" + x for x in a.re]
    k2 = a.kw2 + ["re:" + x for x in a.re2]
    h1 = scan(k1, "1차 신호군") if k1 else set()
    h2 = scan(k2, "2차 신호군") if k2 else set()
    if h1 and h2:
        x = h1 & h2
        print(f"★ 교집합(1차 × 2차): {len(x):,}명 ({len(x)/n*100:.2f}%) → 니모트론 환산 ≈ {round(len(x)*scale):,}명"
              f"  ← 보통 캠페인의 심장\n")

    # ── 문맥 샘플 — 의미 오탐을 잡는 유일한 수단 ──
    # 앞 N개(first-N)를 뽑으면 분포 표본이 아니다. '쇼핑' 850건 중 첫 5건이 우연히
    # 온라인이면 "오탐 없음"으로 오판한다. 그래서 매칭 전체에서 무작위로 뽑는다.
    rnd = random.Random(a.seed)
    print("=== 문맥 샘플 (무작위) — 과녁/비과녁을 세어라 ===")
    print("    카운트만 믿지 마라. 아래 샘플 중 몇 개가 '진짜 그 뜻'인지 세서")
    print("    카운트에 곱해라. 과녁 30% 미만이면 그 키워드는 버리고 더 좁게 다시 스캔.\n")
    for k in (k1 + k2):
        m = matcher(k)
        hits = [(t, m(t)) for r, t in T if m(t) >= 0]
        if not hits:
            continue
        for t, i in rnd.sample(hits, min(a.samples, len(hits))):
            print(f"  [{k[:24]}] …{t[max(0,i-30):i+50]}…".replace("\n", " "))
        print(f"       ↑ {len(hits):,}건 중 무작위 {min(a.samples,len(hits))}건. 과녁 __/{min(a.samples,len(hits))} → 보정 카운트 ≈ ___\n")


if __name__ == "__main__":
    main()
