# fusion/ — composenemotron 2차 합성 데이터·스크립트

니모트론 패널(`nemotron-panel-synthesis` 산출 `panel.json`) 위에 **트렌드·웹·외부 실측·소셜 맥락**을 얹는 2차 합성용 공개 자료.
**정량(설문) 매칭은 없다** — 사실 근거는 니모트론 원본 `[Q]`뿐이고, 브랜드 이력·카테고리 이용·SNS 이용은 `[가설]`로 낮춰 FGD에서 검증한다.

| 경로 | 내용 | 태그 |
|---|---|---|
| `trends/*.md` | 공개 발행 트렌드 리포트 **요약** 24건(오픈서베이·한국리서치·한국갤럽·엠브레인·메조미디어 등). 머리말 title·key·publisher·published·axes·ages | `[T:리포트]` |
| `external/time_use/` | 통계청 2024 생활시간조사 결과(2025-07) **공표 통계표**를 셀 표로 옮긴 것(성×연령대·성×취업 × 요일 × 행동) | `[X:생활시간]` |
| `external/naver_datalab/` | 네이버 데이터랩 검색어트렌드 상대지수(샘플: 커피 카테고리 5그룹, 성×연령 18셀, 2025-10~2026-09 월별) | `[X:데이터랩]` |
| `scripts/` | `fusion.py`(merge·verify·render) · `external.py`(니모트론 셀 → 집계 실측, Apify 소셜·급상승 요약) · `trends.py`(요약 검색·연령 적합) | |

## 공개 범위 원칙

- **원본 PDF는 올리지 않는다** — 각 발행처 저작물. 요약 md의 `원문` URL로 확인한다.
- **설문 원자료·클라이언트 업무 자료·마이크로데이터는 올리지 않는다.** 여기 있는 건 공개 통계표와 공개 리포트 요약, 상대지수 집계뿐이다.
- **API 키·토큰은 넣지 않는다.** Apify·네이버 API는 실행 환경의 연결·환경변수로만 쓴다.
- 소셜 수집(Apify)은 실행마다 그 산출 폴더에 **집계만** 남긴다 — 인스타 계정명·본문 원문은 저장하지 않는다. 유튜브는 공개 채널명(상위 8개)·제목까지.

## 셀 규칙 (`external.cell_of`)

니모트론 원본 필드로 만든다: `sex`(남/여) · `age_band`(통계 원표 기준 — 19세는 10대) · `emp`(economic_activity_status: 취업자 → 취업, 실업자·비경제활동인구 → 비취업) · `hh`(family_type → 1인/부부/부부+자녀/부모동거/기타).
데이터랩 `ratio`는 셀마다 따로 최댓값 100으로 정규화된 **상대값**이다. 셀 간 비교는 앵커 대비 `vs_anchor`로만 한다.

## 쓰는 법

```python
import sys; sys.path.insert(0, "fusion/scripts")
import fusion as fu
fused = fu.merge("<out>/panel.json", authored, {"brand": "...", "category": "...", "sources": [...]})
fu.verify(fused, "<out>/panel.json")     # 실패 시 AssertionError — 고치고 다시
fu.save(fused, "<out>")                  # personas_fused.json + personas_fused.html
```
`authored` 스키마는 `scripts/fusion.py` 머리 주석에 있다. 위치를 바꾸려면 `NEMO_TRENDS_DIR`·`NEMO_EXTERNAL_DIR`.
