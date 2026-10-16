# -*- coding: utf-8 -*-
"""
nemotron.parquet 원격 로더 — 로컬 원본 없이 GitHub(untitled84/nemotron-data)에서
'필요한 바이트 구간만' 받아 원본과 바이트 단위로 동일한 희소(sparse) 파일을 만든다.

원리
  원본 2.85GB는 72개 row group이 빈틈없이 이어져 있고, 각 rg 안에서
  구조형 35컬럼(uuid~neuroticism)과 서술형 16컬럼(cultural_background~)이 앞뒤로 갈린다.
  그래서 원본을 [head | rg00_s | rg00_t | ... | rg71_s | rg71_t | footer] 146조각으로
  '재인코딩 없이' 잘라 parts/ 에 올렸다(manifest.json에 offset·length·sha256).
  이 모듈은 원본 크기의 빈 파일을 만들고, nemotron_reader가 실제로 읽는 컬럼이 속한
  조각만 내려받아 원래 offset에 써 넣는다. 리더는 원본을 읽을 때와 같은 위치에서 같은 바이트를 읽는다.

사용
  from nemotron_remote import open_nemotron
  npq = open_nemotron()                      # 로컬 경로가 없으면 원격
  npq = open_nemotron("/path/nemotron.parquet")  # 로컬 원본이 있으면 그대로 사용
  npq.prefetch(range(72), "struct")         # (선택) 구조형 전수 집계 전에 병렬로 미리 받기

환경변수
  NEMOTRON_GH_REPO  기본 untitled84/nemotron-data
  NEMOTRON_CACHE    기본 ~/.cache/nemotron
다운로드는 gh CLI(`gh api ... contents`)로 한다. 조각마다 sha256을 검증한다.
"""
import os, json, hashlib, subprocess, threading
from concurrent.futures import ThreadPoolExecutor
from nemotron_reader import NemotronParquet

REPO = os.environ.get("NEMOTRON_GH_REPO", "untitled84/nemotron-data")
CACHE = os.path.expanduser(os.environ.get("NEMOTRON_CACHE", "~/.cache/nemotron"))
_lock = threading.Lock()


def _gh_raw(path):
    r = subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw", f"repos/{REPO}/contents/{path}"],
        capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"다운로드 실패 {path}: {r.stderr.decode('utf-8','replace')[:300]}")
    return r.stdout


class RemoteNemotronParquet(NemotronParquet):
    def __init__(self, cache=CACHE, workers=4):
        os.makedirs(cache, exist_ok=True)
        self.cache = cache; self.workers = workers
        mpath = os.path.join(cache, "manifest.json")
        if not os.path.exists(mpath):
            open(mpath, "wb").write(_gh_raw("manifest.json"))
        self.manifest = json.load(open(mpath))
        self.parts = {p["name"]: p for p in self.manifest["parts"]}
        self.local = os.path.join(cache, "nemotron.parquet")
        if not os.path.exists(self.local) or os.path.getsize(self.local) != self.manifest["size"]:
            with open(self.local, "wb") as f:
                f.truncate(self.manifest["size"])        # 희소 파일: 실제 디스크는 받은 만큼만 쓴다
            self._save_have(set())
        self.have = self._load_have()
        self._ensure(["head.bin", "footer.bin"])
        super().__init__(self.local)
        # 컬럼 이름 → 구조형/서술형 판별 (스키마 순서 기준)
        first_text = self.manifest["text_first_column"]
        names = [".".join(p.decode() for p in c.get(3, {}).get(3, [])) for c in self.rgs[0].get(1, [])]
        cut = names.index(first_text)
        self.kind_of = {n: ("struct" if i < cut else "text") for i, n in enumerate(names)}

    # ---- 상태 ----
    def _have_path(self): return os.path.join(self.cache, "have.json")
    def _load_have(self):
        try: return set(json.load(open(self._have_path())))
        except Exception: return set()
    def _save_have(self, s): json.dump(sorted(s), open(self._have_path(), "w"))

    # ---- 다운로드 ----
    def _fetch_one(self, name):
        p = self.parts[name]
        b = _gh_raw(f"parts/{name}")
        if len(b) != p["length"] or hashlib.sha256(b).hexdigest() != p["sha256"]:
            raise RuntimeError(f"무결성 검증 실패: {name}")
        with _lock:
            with open(self.local, "r+b") as f:
                f.seek(p["offset"]); f.write(b)
            self.have.add(name); self._save_have(self.have)

    def _ensure(self, names):
        need = [n for n in names if n not in self.have]
        if not need: return
        with ThreadPoolExecutor(self.workers) as ex:
            list(ex.map(self._fetch_one, need))
        if hasattr(self, "f"):                       # 새로 쓴 바이트가 보이도록 핸들 갱신
            self.f.close(); self.f = open(self.local, "rb")

    def prefetch(self, rg_indices, kind="struct"):
        kinds = ["struct", "text"] if kind == "all" else [kind]
        self._ensure([f"rg{i:02d}_{'s' if k == 'struct' else 't'}.bin" for i in rg_indices for k in kinds])

    def read_column(self, rg_index, name):
        k = self.kind_of.get(name)
        if k is None: raise KeyError(name)
        self._ensure([f"rg{rg_index:02d}_{'s' if k == 'struct' else 't'}.bin"])
        return super().read_column(rg_index, name)

    def downloaded_mb(self):
        return sum(self.parts[n]["length"] for n in self.have) / 1e6


def open_nemotron(path=None):
    """로컬 원본이 있으면 그걸, 없으면 원격 희소 파일을 연다. 반환 객체의 API는 동일하다."""
    if path and path not in ("gh", "remote") and os.path.exists(path):
        return NemotronParquet(path)
    return RemoteNemotronParquet()
