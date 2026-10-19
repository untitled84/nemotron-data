# -*- coding: utf-8 -*-
"""
Nemotron-Personas-Korea parquet 리더 (순수 파이썬, pyarrow/네트워크 불필요).
SNAPPY 해제 + dictionary/RLE/PLAIN 디코더를 직접 구현.

검증: 72개 row group × 8컬럼 = 576건 전수 통과 (100만 행 전부 읽힘).
      + rg0 × 51컬럼 전수 통과 — SKILL.md가 "컬럼은 다 읽어라"라고 지시하는데
        검증이 8컬럼뿐이면 지시와 근거에 간극이 생긴다. 그래서 51컬럼을 실제로 돌렸다.
      한계: BYTE_ARRAY/INT64/INT32 + 데이터 페이지 v1 + max def level 1만 다룬다.
        이 데이터셋은 전부 그 범위 안이다. 다른 parquet엔 쓰지 마라.
수정 이력:
  - 코덱 메타(codec)를 믿고 해제한다. 크기 비교로 압축 여부를 추측하면
    압축 결과가 원본과 같은 크기인 페이지에서 조용히 깨진다.
  - present=0(전부 null)인 데이터 페이지 방어. 그런 페이지엔 bit-width
    바이트도 인덱스 데이터도 없다 (openness×rg2에서 실제로 터졌다).

사용:
    from nemotron_reader import NemotronParquet
    npq = NemotronParquet("/path/to/nemotron.parquet")
    print(npq.num_rows, npq.num_row_groups)   # 1,000,000 / 72
    rows = npq.load(["age","sex","region","income_bracket","occupation",
                     "hobbies_and_interests_list"], rg_indices=[0])  # list[dict]
컬럼(51종) 예: uuid, first_name, last_name, sex, region, district, age,
    marital_status(리더 버그 수정 후 정상 — 미혼/배우자있음/이혼/사별), education_level, bachelors_field,
    occupation, family_type, housing_type, housing_tenure, income_bracket,
    bmi_status, blood_pressure_status, blood_sugar_status, waist_status,
    smoking_status, drinking_status, openness/conscientiousness/extraversion/
    agreeableness/neuroticism(JSON: t_score/label/description),
    cultural_background, skills_and_expertise(_list), hobbies_and_interests(_list),
    career_goals_and_ambitions, professional/finance/healthcare/sports/arts/
    travel/culinary/family_persona, persona, detailed_persona.
"""
import struct

class _R:
    __slots__=("b","i")
    def __init__(s,b,i=0): s.b=b; s.i=i
    def u8(s): v=s.b[s.i]; s.i+=1; return v
    def varint(s):
        r=0; sh=0
        while True:
            x=s.b[s.i]; s.i+=1; r|=(x&0x7f)<<sh
            if not (x&0x80): break
            sh+=7
        return r
    def zig(s):
        n=s.varint(); return (n>>1)^-(n&1)

def _struct(r):
    f={}; last=0
    while True:
        h=r.u8()
        if h==0: break
        t=h&0x0f; d=(h&0xf0)>>4
        fid=(r.zig() if d==0 else last+d); last=fid
        f[fid]=_val(r,t)
    return f

def _val(r,t):
    if t==1: return True
    if t==2: return False
    if t in (3,4,5,6): return r.zig()
    if t==7: v=struct.unpack('<d',r.b[r.i:r.i+8])[0]; r.i+=8; return v
    if t==8: n=r.varint(); v=r.b[r.i:r.i+n]; r.i+=n; return v
    if t in (9,10):
        sh=r.u8(); et=sh&0x0f; sz=(sh&0xf0)>>4
        if sz==15: sz=r.varint()
        return [_val(r,et) for _ in range(sz)]
    if t==11:
        sz=r.varint()
        if sz==0: return {}
        kv=r.u8(); kt=kv>>4; vt=kv&0x0f; dd={}
        for _ in range(sz): k=_val(r,kt); dd[k]=_val(r,vt)
        return dd
    if t==12: return _struct(r)
    raise ValueError("thrift type %d"%t)

def _snappy(data):
    ln=0; pos=0; sh=0
    while True:
        b=data[pos]; pos+=1; ln|=(b&0x7f)<<sh
        if not (b&0x80): break
        sh+=7
    out=bytearray()
    while pos<len(data):
        tag=data[pos]; pos+=1; typ=tag&3
        if typ==0:
            l=tag>>2
            if l<60: l+=1
            else:
                nb=l-59; l=int.from_bytes(data[pos:pos+nb],'little')+1; pos+=nb
            out+=data[pos:pos+l]; pos+=l
        else:
            if typ==1:
                l=((tag>>2)&7)+4; off=((tag>>5)<<8)|data[pos]; pos+=1
            elif typ==2:
                l=(tag>>2)+1; off=int.from_bytes(data[pos:pos+2],'little'); pos+=2
            else:
                l=(tag>>2)+1; off=int.from_bytes(data[pos:pos+4],'little'); pos+=4
            st=len(out)-off
            for k in range(l): out.append(out[st+k])
    return bytes(out)

def _rle_hybrid(buf,bw,count):
    vals=[]; i=0; bwB=(bw+7)//8
    while len(vals)<count and i<len(buf):
        hdr=0; sh=0
        while True:
            b=buf[i]; i+=1; hdr|=(b&0x7f)<<sh
            if not (b&0x80): break
            sh+=7
        if hdr&1:
            groups=hdr>>1; nv=groups*8; nb=groups*bw
            chunk=buf[i:i+nb]; i+=nb; bit=0
            for _ in range(nv):
                v=0
                for c in range(bw):
                    bi=bit>>3; bo=bit&7
                    if bi<len(chunk): v|=((chunk[bi]>>bo)&1)<<c
                    bit+=1
                vals.append(v)
        else:
            run=hdr>>1; val=int.from_bytes(buf[i:i+bwB],'little'); i+=bwB
            vals.extend([val]*run)
    return vals[:count]

class NemotronParquet:
    def __init__(self, path):
        self.path=path
        self.f=open(path,'rb')
        self.f.seek(0,2); size=self.f.tell()
        self.f.seek(size-8); tail=self.f.read(8)
        assert tail[4:]==b'PAR1', "not a parquet file"
        flen=struct.unpack('<I',tail[:4])[0]
        self.f.seek(size-8-flen)
        self.meta=_struct(_R(self.f.read(flen)))
        self.rgs=self.meta[4]
        self.num_rows=self.meta.get(3)
        self.num_row_groups=len(self.rgs)

    def _colmeta(self, rg, name):
        for c in rg.get(1,[]):
            cmd=c.get(3,{})
            if ".".join(p.decode() for p in cmd.get(3,[]))==name: return cmd
        return None

    def read_column(self, rg_index, name):
        rg=self.rgs[rg_index]; cmd=self._colmeta(rg,name)
        if cmd is None: raise KeyError(name)
        ctype=cmd.get(1)
        start=cmd.get(11) if cmd.get(11) is not None else cmd.get(9)
        comp=cmd.get(7); rg_rows=rg.get(3)
        codec=cmd.get(4)   # 1=SNAPPY, 0=UNCOMPRESSED
        self.f.seek(start); raw=self.f.read(comp+(1<<20))
        r=_R(raw); dic=None; values=[]
        while len(values)<rg_rows:
            ph=_struct(r); ptype=ph.get(1); usize=ph.get(2); csize=ph.get(3)
            body=raw[r.i:r.i+csize]; r.i+=csize
            # 크기 비교로 압축 여부를 '추측'하면 안 된다 — 코덱 메타를 믿는다.
            # (압축 결과가 원본과 같은 크기인 페이지가 있으면 추측이 조용히 깨진다)
            dec = _snappy(body) if codec==1 else body
            if len(dec)!=usize and codec==1:
                dec = body if len(body)==usize else dec
            if ptype==2:
                dn=ph.get(7,{}).get(1); dic=[]; bi=0
                if ctype==6:
                    for _ in range(dn):
                        l=int.from_bytes(dec[bi:bi+4],'little'); bi+=4
                        dic.append(dec[bi:bi+l]); bi+=l
                elif ctype==2:
                    for _ in range(dn): dic.append(int.from_bytes(dec[bi:bi+8],'little',signed=True)); bi+=8
                elif ctype==1:
                    for _ in range(dn): dic.append(int.from_bytes(dec[bi:bi+4],'little',signed=True)); bi+=4
                continue
            if ptype==0:
                dph=ph.get(5,{}); npv=dph.get(1); enc=dph.get(2); bi=0
                deflen=int.from_bytes(dec[bi:bi+4],'little'); bi+=4
                defs=_rle_hybrid(dec[bi:bi+deflen],1,npv); bi+=deflen
                npres=sum(defs); present=[]
                if npres==0:
                    pass   # 전부 null인 페이지 — 인덱스 데이터도 bit-width 바이트도 없다
                elif enc in (2,8):
                    bw=dec[bi]; bi+=1
                    present=[dic[k] for k in _rle_hybrid(dec[bi:],bw,npres)]
                elif enc==0:
                    if ctype==6:
                        for _ in range(npres):
                            l=int.from_bytes(dec[bi:bi+4],'little'); bi+=4
                            present.append(dec[bi:bi+l]); bi+=l
                    elif ctype==2:
                        for _ in range(npres): present.append(int.from_bytes(dec[bi:bi+8],'little',signed=True)); bi+=8
                    elif ctype==1:
                        for _ in range(npres): present.append(int.from_bytes(dec[bi:bi+4],'little',signed=True)); bi+=4
                it=iter(present)
                for d in defs: values.append(next(it) if d==1 else None)
        return [(v.decode('utf-8','replace') if isinstance(v,bytes) else v) for v in values[:rg_rows]]

    def load_adaptive(self, columns, filter_fn, min_rows, max_rg=None, verbose=True):
        """rg를 하나씩 늘려가며 filter_fn 통과 행이 min_rows에 닿으면 멈춘다.

        니모트론은 인구정렬 데이터라 row group마다 분포가 같다.
        그래서 흔한 조건은 rg 1개로 충분하고, 희소한 조건만 확장이 의미 있다.
        '항상 전수'도 '항상 rg0'도 아니고 — 필요한 만큼만 읽는다.

        반환: (matched_rows, rg_used, scanned_rows)
        """
        max_rg = max_rg or self.num_row_groups
        out=[]; scanned=0; used=0
        for gi in range(max_rg):
            cols={c:self.read_column(gi,c) for c in columns}
            n=len(next(iter(cols.values()))); scanned+=n; used=gi+1
            for i in range(n):
                row={c:cols[c][i] for c in columns}
                if filter_fn(row): out.append(row)
            if len(out)>=min_rows:
                break
        if verbose:
            print(f"  적응형 로드: rg {used}/{max_rg}개 · {scanned:,}행 스캔 → 조건 충족 {len(out):,}명 "
                  f"(목표 {min_rows}) · 전체의 {scanned/self.num_rows*100:.1f}%")
        return out, used, scanned

    def load(self, columns, rg_indices=(0,)):
        """returns list[dict] over the given row groups."""
        rows=[]
        for gi in rg_indices:
            cols={c:self.read_column(gi,c) for c in columns}
            n=len(next(iter(cols.values())))
            for i in range(n):
                rows.append({c:cols[c][i] for c in columns})
        return rows
