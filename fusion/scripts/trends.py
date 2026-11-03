# -*- coding: utf-8 -*-
"""트렌드 리포트 요약 라이브러리 (fusion/trends/*.md) — composenemotron 2차 합성의 [T:리포트] 소스.
원본 PDF는 이 공개 저장소에 없다(발행처 저작물). 요약 md의 '원문' URL로 확인한다.

    import trends
    lib = trends.load()                         # [{title,key,publisher,published,axes,ages,path,text}, ...]
    trends.find(lib, "카페", "커피", axis="소비")   # 제목·축·본문 키워드 매칭 (OR), axis는 축 필터
    trends.fits_age(doc, 25)                    # '적용 가능 페르소나 연령' 범위 안인지
    print(trends.table(lib))                    # 목록
    trends.pdf_text("<로컬 PDF 경로>", pages="1-5")   # 사용자가 따로 가진 원본 PDF가 있을 때만

CLI:  python3 trends.py list | find 카페 커피 --axis 소비 --age 25
위치: $NEMO_TRENDS_DIR → fusion/trends (이 파일의 ../trends)
"""
import os, re, sys, pathlib

_HERE = pathlib.Path(__file__).resolve().parent


def trends_dir():
    d = os.environ.get("NEMO_TRENDS_DIR")
    return pathlib.Path(d) if d else _HERE.parent / "trends"


def _parse(p):
    t = p.read_text(encoding="utf-8")
    meta, body = {}, t
    if t.startswith("---"):
        _, fm, body = t.split("---", 2)
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    meta["path"] = str(p)
    meta["text"] = body.strip()
    return meta


def load():
    d = trends_dir()
    return sorted((_parse(p) for p in d.glob("*.md") if p.name.lower() != "readme.md"),
                  key=lambda m: m.get("published", ""), reverse=True)


def find(lib, *words, axis=None):
    out = []
    for m in lib:
        hay = " ".join([m.get("title", ""), m.get("axes", ""), m.get("text", "")])
        if words and not any(w in hay for w in words):
            continue
        if axis and axis not in m.get("axes", ""):
            continue
        out.append(m)
    return out


def fits_age(m, age):
    """'19~59세', '19세 이상', '20~39세' 등에서 범위를 읽어 age가 들어가는지. 못 읽으면 None."""
    s = m.get("ages", "").replace("\\~", "~")
    r = re.search(r"(\d+)\s*~\s*(\d+)\s*세", s)
    if r:
        return int(r.group(1)) <= age <= int(r.group(2))
    r = re.search(r"(\d+)\s*세\s*이상", s)
    if r:
        return age >= int(r.group(1))
    return None


def pdfs():
    """trends/pdf/index.csv → [{file,title,publisher,published,summary,path}] (summary = 짝 요약 md, 없으면 '')."""
    import csv
    idx = trends_dir() / "pdf" / "index.csv"
    if not idx.exists():
        return []
    with open(idx, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["path"] = str(trends_dir() / "pdf" / r["file"])
    return rows


def pdf_text(name, pages=None):
    """원본 PDF 텍스트. pages='3-7' 처럼 범위 지정 가능. pdftotext 우선, 없으면 pypdf."""
    import subprocess, shutil
    p = pathlib.Path(name)
    if not p.exists():
        p = trends_dir() / "pdf" / name
    a, b = (pages.split("-") + [None])[:2] if pages else (None, None)
    if shutil.which("pdftotext"):
        cmd = ["pdftotext", "-layout"]
        if a: cmd += ["-f", a, "-l", b or a]
        return subprocess.run(cmd + [str(p), "-"], capture_output=True, text=True).stdout
    from pypdf import PdfReader
    rd = PdfReader(str(p)); lo = int(a) - 1 if a else 0; hi = int(b or a) if a else len(rd.pages)
    return "\n".join(pg.extract_text() or "" for pg in rd.pages[lo:hi])


def pdf_grep(*words):
    """모든 원본 PDF에서 단어가 나오는 페이지 → [(file, page, 줄)]"""
    hits = []
    for r in pdfs():
        txt = pdf_text(r["path"])
        for i, pg in enumerate(txt.split("\f"), 1):
            for line in pg.splitlines():
                if any(w in line for w in words):
                    hits.append((r["file"], i, line.strip()[:120]))
    return hits


def table(lib):
    return "\n".join(f"{m.get('published','')}  {m.get('publisher','')[:14]:14}  {m.get('title','')[:46]:46}  축: {m.get('axes','')[:40]}  연령: {m.get('ages','')[:24]}" for m in lib)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list"); sp.add_parser("pdfs")
    g = sp.add_parser("pdfgrep"); g.add_argument("words", nargs="+")
    f = sp.add_parser("find"); f.add_argument("words", nargs="*"); f.add_argument("--axis"); f.add_argument("--age", type=int)
    a = ap.parse_args()
    lib = load()
    if a.cmd == "pdfs":
        for r in pdfs(): print(f"{r['published']:10}  {r['file']:52}  요약: {r['summary'] or '없음'}")
        raise SystemExit
    if a.cmd == "pdfgrep":
        for f_, pg, ln in pdf_grep(*a.words): print(f"{f_} p{pg}: {ln}")
        raise SystemExit
    if a.cmd == "list":
        print(f"{len(lib)}건 · {trends_dir()}"); print(table(lib))
    else:
        r = find(lib, *a.words, axis=a.axis)
        if a.age is not None:
            r = [m for m in r if fits_age(m, a.age) is not False]
        print(f"{len(r)}건"); print(table(r))
