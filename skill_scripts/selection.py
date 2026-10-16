# -*- coding: utf-8 -*-
"""선발 기록 + 선발 감사 — "왜 이 사람인가"를 산출물 밖에 남기고, 선발 자체의 쏠림을 잰다.

왜 있나:
  이 스킬은 합성에는 엄격하다(모든 값에 Q/INF 태그, 근거 병기, axis_audit).
  그런데 선발은 그 규율 밖이었다 — 후보 85명 중 왜 이 3명인지가 어디에도 안 남았다.
  (1) 같은 브리프를 다시 돌리면 다른 3명이 나와도 비교할 근거가 없고
  (2) "이 사람은 왜 뽑혔어요?"에 "세그 조건에 맞아서"(85명이 다 맞는데)밖에 못 답하고
  (3) 세그 3명이 비슷할 때 데이터 탓인지 점수식 탓인지 가를 수 없었다.
  axis_audit는 합성 축의 쏠림을 재지만 선발의 쏠림은 못 잰다.

원칙 — 보여주는 산출물은 건드리지 않는다:
  panel.html · panel.json · panel_carriers.xlsx의 형식·내용은 그대로다.
  이 모듈은 **별도 파일 둘**을 만든다: selection_log.json(기계용) · selection_audit.md(사람용).
  점수식은 여전히 프로젝트마다 판단으로 짠다 — 틀로 고정하지 않는다. 다만 **기록은 남긴다**.

두 기능:
  A. log_selection(...)  — 세그별 점수식·후보 전원 점수·순위·선발 여부·rg·스캔 규모를 기록
  C. audit_selection(...) — 선발된 N명이 후보 풀 대비 어느 쪽으로 쏠렸는지 측정
       · 구조형 필드(연령·성별·지역·소득·직업·학력·가구·주거·경활)별로
         [후보 풀에서의 비율] vs [선발 N명에서의 비율]을 비교
       · 세그 정의(하드 필터)에 쓴 필드는 제외한다 — "20대 여성" 세그가 전원 여성인 건 쏠림이 아니다
       · 판정(표시 정수 %로 — axis_audit와 같은 이유):
           🔴 선발 쏠림: 선발 내 최빈값 점유율 ≥78% **이고** 그 값의 풀 내 비율이 그보다 30%p 이상 낮음
                        → 풀에 없던 집중을 점수식이 만들었다. 고치기 전엔 산출 금지(종료코드 1).
           🟡 주의:     선발 점유율 56~77% 이고 풀 대비 +20%p 이상
           🟢 정상:     그 외 (풀도 그렇게 생겼으면 선발이 그런 건 정상이다)
           ⚪ 감수:     --accepted 로 사용자가 감수한 필드
       · 스코어 천장: 선발 N명의 점수가 전부 동점이면 🔴 — SKILL 5단계 "상위 N이 동점이면
         확장을 멈추고 스코어를 고쳐라". 동점 뒤에 더 있는 동점자는 '사실상 무작위 선발'이다.
       · 연령은 평균 차이를 풀 표준편차로 나눠 본다(|d| ≥ 1.0 🔴, ≥ 0.6 🟡).

사용 (5단계에서, 세그마다):
    from selection import log_selection, audit_selection, write_audit_md
    rec = log_selection(seg="코어게이머", pool=pool_rows, scores=score_dict,
                        chosen=[u1,u2,u3], formula={"설명": "...", "keywords": {...}, "big5": {...}},
                        hard_filter={"sex": "남자", "age": "19-29"}, rg_used=2, scanned=27818)
    recs.append(rec)
    ...
    save_log(recs, "<outputs>/selection_log.json")
    flags = audit_selection(recs, accepted=[...])
    write_audit_md(recs, flags, "<outputs>/selection_audit.md")
    # flags에 🔴가 있으면 산출 전에 점수식을 고친다

CLI (기록된 로그만 다시 감사):
    python3 selection.py <selection_log.json> [--accepted 필드 ...] [--md out.md]
"""
import argparse, json, statistics, sys
from collections import Counter

STRUCT_FIELDS = ["age", "sex", "region", "income_bracket", "occupation",
                 "education_level", "family_type", "housing_tenure",
                 "economic_activity_status", "marital_status"]
KEEP_IN_LOG = ["uuid", "age", "sex", "region", "district", "occupation", "income_bracket",
               "education_level", "family_type", "housing_tenure", "economic_activity_status",
               "marital_status"]


def _pct(x, n):
    return round(x * 100 / n) if n else 0


# ---------------------------------------------------------------- A. 기록
def log_selection(seg, pool, scores, chosen, formula, hard_filter=None, rg_used=None,
                  scanned=None, note=""):
    """한 세그의 선발 기록을 dict로 만든다.

    pool    : 하드 필터를 통과한 후보 행(dict) 리스트 — uuid 필수, 구조형 필드 있으면 같이 기록
    scores  : {uuid: 점수}. pool에 있는데 점수가 없으면 0으로 간주하고 '점수 없음'으로 표시
    chosen  : 선발된 uuid 리스트(순서 = 최종 순위)
    formula : 점수식. 자유 형식 dict — 최소한 {"설명": "..."}는 넣는다.
              키워드식이면 {"keywords": {컬럼: {키워드: 가중치}}}, Big5면 {"big5": {특성: 가중치}} 권장
    hard_filter : 세그 정의에 쓴 필드와 조건 — 감사에서 이 필드는 제외된다
    """
    chosen = list(chosen)
    byu = {r["uuid"]: r for r in pool}
    missing = [u for u in chosen if u not in byu]
    if missing:
        raise ValueError(f"선발 uuid가 후보 풀에 없음: {missing[:3]} — 풀 밖에서 뽑았거나 uuid가 틀렸다")
    ranked = sorted(pool, key=lambda r: (-float(scores.get(r["uuid"], 0)), r["uuid"]))
    rank = {r["uuid"]: i + 1 for i, r in enumerate(ranked)}
    cand = []
    for r in ranked:
        row = {k: r.get(k) for k in KEEP_IN_LOG if k in r}
        row["score"] = scores.get(r["uuid"], None)
        row["rank"] = rank[r["uuid"]]
        row["chosen"] = r["uuid"] in chosen
        cand.append(row)
    sc = [float(scores.get(u, 0)) for u in chosen]
    pool_sc = [float(v) for v in scores.values()]
    return {
        "seg": seg,
        "hard_filter": hard_filter or {},
        "formula": formula,
        "rg_used": rg_used, "scanned": scanned,
        "pool_size": len(pool),
        "n_chosen": len(chosen),
        "chosen": chosen,
        "chosen_scores": sc,
        "chosen_ranks": [rank[u] for u in chosen],
        "score_dist": {
            "max": max(pool_sc) if pool_sc else None,
            "median": statistics.median(pool_sc) if pool_sc else None,
            "n_at_max": sum(1 for v in pool_sc if pool_sc and v == max(pool_sc)),
            "top10": [c["score"] for c in cand[:10]],
        },
        "note": note,
        "candidates": cand,
    }


def save_log(records, path):
    json.dump({"version": 1, "segments": records}, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return path


# ---------------------------------------------------------------- C. 감사
def _judge_cat(ch_share, pool_share, accepted):
    cp, pp = _pct(ch_share, 1), _pct(pool_share, 1)
    if accepted:
        return "⚪"
    if cp >= 78 and cp - pp >= 30:
        return "🔴"
    if cp >= 56 and cp - pp >= 20:
        return "🟡"
    return "🟢"


def audit_selection(records, accepted=()):
    """세그별 선발 쏠림 측정. 반환: flags 리스트(dict). 🔴가 하나라도 있으면 산출 금지."""
    accepted = set(accepted or ())
    flags = []
    for rec in records:
        seg = rec["seg"]; cand = rec["candidates"]
        chosen = [c for c in cand if c["chosen"]]
        n, N = len(chosen), len(cand)
        skip = set(rec.get("hard_filter", {}).keys())
        # 스코어 천장
        sc = rec.get("chosen_scores") or []
        if n >= 2 and len(set(sc)) == 1:
            n_tied = sum(1 for c in cand if c.get("score") is not None and float(c["score"]) == float(sc[0]))
            flags.append({"seg": seg, "field": "score", "level": "🔴",
                          "msg": f"선발 {n}명 전원 동점({sc[0]}) — 풀에서 같은 점수가 {n_tied}명. "
                                 f"상위 N 동점은 사실상 무작위 선발이다. 점수식을 더 정교하게."})
        # 순위 밖 선발 — 점수식과 실제 선발이 어긋남 (눈으로 집었거나 점수식이 기록과 다름)
        rk = rec.get("chosen_ranks") or []
        if n >= 1 and rk and max(rk) > max(n * 3, n + 5):
            flags.append({"seg": seg, "field": "rank", "level": "🟡",
                          "msg": f"선발 순위 {sorted(rk)} — 상위 {n}명이 아니다. 점수식 밖의 판단으로 뽑았다면 "
                                 f"그 사유를 note에 남겨라(기록된 점수식과 실제 선발이 어긋나면 기록이 거짓이 된다)."})
        elif n >= 2 and rec["score_dist"].get("n_at_max", 0) > n:
            flags.append({"seg": seg, "field": "score", "level": "🟡",
                          "msg": f"최고점 동점자 {rec['score_dist']['n_at_max']}명 > 선발 {n}명 — "
                                 f"1위 안에서 누가 뽑혔는지는 uuid 순이다. 점수식에 변별 항을 더 넣어라."})
        for f in STRUCT_FIELDS:
            if f in skip or f == "age":
                continue
            vals_pool = [c.get(f) for c in cand if c.get(f) not in (None, "")]
            vals_ch = [c.get(f) for c in chosen if c.get(f) not in (None, "")]
            if not vals_pool or not vals_ch:
                continue
            top, cnt = Counter(vals_ch).most_common(1)[0]
            ch_share = cnt / len(vals_ch)
            pool_share = Counter(vals_pool)[top] / len(vals_pool)
            lv = _judge_cat(ch_share, pool_share, f in accepted)
            flags.append({"seg": seg, "field": f, "level": lv, "value": str(top),
                          "chosen_pct": _pct(ch_share, 1), "pool_pct": _pct(pool_share, 1),
                          "msg": f"'{top}' 선발 {cnt}/{len(vals_ch)}({_pct(ch_share,1)}%) vs 풀 {_pct(pool_share,1)}%"})
        if "age" not in skip:
            ap = [c["age"] for c in cand if isinstance(c.get("age"), (int, float))]
            ac = [c["age"] for c in chosen if isinstance(c.get("age"), (int, float))]
            if len(ap) >= 2 and ac:
                sd = statistics.pstdev(ap) or 1.0
                d = (statistics.mean(ac) - statistics.mean(ap)) / sd
                lv = "⚪" if "age" in accepted else ("🔴" if abs(d) >= 1.0 else "🟡" if abs(d) >= 0.6 else "🟢")
                flags.append({"seg": seg, "field": "age", "level": lv, "d": round(d, 2),
                              "msg": f"선발 평균 {statistics.mean(ac):.1f}세 vs 풀 평균 {statistics.mean(ap):.1f}세 "
                                     f"(풀 표준편차 {sd:.1f}, d={d:+.2f})"})
    return flags


def has_red(flags):
    return any(f["level"] == "🔴" for f in flags)


def write_audit_md(records, flags, path):
    L = ["# 선발 기록·감사 (부속 — 패널 산출물과 별개)", ""]
    L.append("이 파일은 **왜 이 사람들이 뽑혔는지**와 **선발이 후보 풀 대비 어디로 쏠렸는지**를 남긴다. "
             "panel.html / panel.json / panel_carriers.xlsx는 바꾸지 않는다.")
    L.append("")
    for rec in records:
        L.append(f"## 세그 · {rec['seg']}")
        L.append(f"- 하드 필터: `{json.dumps(rec.get('hard_filter', {}), ensure_ascii=False)}`")
        if rec.get("rg_used") is not None:
            L.append(f"- 읽은 범위: rg {rec['rg_used']}개 · {rec.get('scanned') or '?'}행 스캔 → 후보 **{rec['pool_size']}명**")
        else:
            L.append(f"- 후보 **{rec['pool_size']}명**")
        L.append(f"- 점수식: `{json.dumps(rec['formula'], ensure_ascii=False)}`")
        sd = rec["score_dist"]
        L.append(f"- 점수 분포: 최고 {sd['max']} (동점 {sd['n_at_max']}명) · 중앙값 {sd['median']} · 상위10 {sd['top10']}")
        L.append("")
        L.append("| 순위 | uuid | 점수 | 나이 | 성별 | 직업 | 소득 |")
        L.append("|---|---|---|---|---|---|---|")
        for c in rec["candidates"][:10]:
            mark = "**" if c["chosen"] else ""
            L.append(f"| {c['rank']} | {mark}{str(c.get('uuid'))[:8]}{mark} | {c['score']} | {c.get('age','')} | "
                     f"{c.get('sex','')} | {c.get('occupation','')} | {c.get('income_bracket','')} |")
        extra = [c for c in rec["candidates"][10:] if c["chosen"]]
        for c in extra:
            L.append(f"| {c['rank']} | **{str(c.get('uuid'))[:8]}** | {c['score']} | {c.get('age','')} | "
                     f"{c.get('sex','')} | {c.get('occupation','')} | {c.get('income_bracket','')} |")
        L.append("")
        segflags = [f for f in flags if f["seg"] == rec["seg"]]
        L.append("**선발 쏠림 감사** (하드 필터 필드 제외)")
        L.append("")
        for f in segflags:
            L.append(f"- {f['level']} `{f['field']}` — {f['msg']}")
        L.append("")
    # 세그 간 반복 — n=3에서 2/3 쏠림은 우연(약 11%)일 수 있다. 같은 필드가 여러 세그에서
    # 반복 🟡/🔴이면 우연이 아니라 점수식이 그 필드를 보고 있다는 뜻이다.
    byf = {}
    for f in flags:
        if f["level"] in ("🟡", "🔴") and f["field"] not in ("score", "rank"):
            byf.setdefault(f["field"], set()).add(f["seg"])
    rep = {k: v for k, v in byf.items() if len(v) >= 2}
    if rep:
        L.append("## 세그 간 반복 쏠림")
        L.append("")
        L.append("n=3에서 한 세그의 2/3 쏠림은 우연일 수 있다(약 11%). **같은 필드가 여러 세그에서 반복**되면 점수식이 그 필드로 기울어 있는 것이다.")
        for k, v in rep.items():
            L.append(f"- `{k}` — {len(v)}개 세그에서 반복: {', '.join(sorted(v))}")
        L.append("")
    reds = [f for f in flags if f["level"] == "🔴"]
    L.append("## 판정")
    L.append("")
    if reds:
        L.append(f"🔴 **{len(reds)}건** — 풀에 없던 집중을 점수식이 만들었거나 동점 선발이다. 고치기 전엔 산출하지 않는다.")
        for f in reds:
            L.append(f"  - [{f['seg']}] {f['field']}: {f['msg']}")
    else:
        y = [f for f in flags if f["level"] == "🟡"]
        L.append(f"🟢 통과 (🟡 {len(y)}건 — 산출물에 수치와 함께 기록)")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--accepted", nargs="*", default=[])
    ap.add_argument("--md", default=None)
    a = ap.parse_args()
    recs = json.load(open(a.log, encoding="utf-8"))["segments"]
    flags = audit_selection(recs, a.accepted)
    for f in flags:
        print(f"{f['level']} [{f['seg']}] {f['field']}: {f['msg']}")
    if a.md:
        write_audit_md(recs, flags, a.md); print("→", a.md)
    sys.exit(1 if has_red(flags) else 0)


if __name__ == "__main__":
    main()
