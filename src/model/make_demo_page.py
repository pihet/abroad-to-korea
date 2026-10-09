"""데모 페이지: 서비스 기본값(C, 시군구 vote100, 대표사진 풀)으로 해외 질의를 돌려 정적 HTML 1장을 만든다.

화면
    왼쪽   해외 질의 사진 1장 + Wikimedia Commons 저작자·라이선스 표기
    오른쪽 추천 시군구 상위 5곳. 각 시군구에서 가장 닮은 관광지 사진(원본 비율, 자르기·필터 없음),
           관광지명, 시군구, 공공누리 유형
    아래   선택 월의 시군구별 혼잡도 (P1 월 단위 ridge, HANDOFF 10-1 명세) 막대
질의 사진 고르기: 그 해외지 사진 전체 평균과 가장 닮은 1장 (정답과 무관)
혼잡도 지수: 예측 외지인 방문자 수 / 그 시군구의 최근 12개월 월평균 × 100

실행: .venv/bin/python src/model/make_demo_page.py
결과: docs/demo/index.html (이미지 base64 내장 단일 파일)
"""

import base64
import gzip
import html
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "forecast"))  # p1_spec

import clip_proto as cp
import holdout_pilot as hp
import scene_catalog as sc

QUERIES = ["lisbon", "interlaken"]   # 개발셋 안에서 결과가 자연스러운 질의
TARGET_MONTH = "2026-10"             # 마지막 방문자 데이터(2026-08)의 2개월 뒤 = P1 월 단위 조건
OUT = cp.ROOT / "docs/demo"
VISIT_RAW = cp.ROOT / "data/raw/datalab/locgoRegnVisitrDDList"
LABEL = "프로토타입 · 개발셋 결과"
KOGL = {"Type1": "공공누리 제1유형 (출처표시)", "Type3": "공공누리 제3유형 (출처표시·변경금지)"}
# 방문자수 API 시도 코드 → TourAPI 법정동 시도 코드 (강원·전북 특별자치도, 전남·광주 통합)
VISIT_TO_TOUR_SIDO = {"42": "51", "45": "52", "46": "12", "29": "12"}


# ------------------------------------------------------------------ 추천 (C)
def recommend(I, place, qv_scene, by_scene, scenes_of, extra):
    vs = [v for sid in scenes_of[place] for v in by_scene.get(sid, [])] + extra.get(place, [])
    v = np.mean(vs, 0)
    v /= np.linalg.norm(v)
    scores, sims, _ = sc.vote_scores(I, v)
    out = []
    for ri in np.argsort(-scores, kind="stable")[:5]:
        idx = np.where(I["img_region"] == ri)[0]
        best = idx[np.argmax(sims[idx])]  # 그 시군구에서 가장 닮은 관광지 사진
        it = I["items"][str(I["cid"][best])]
        u = I["regions"][ri]
        out.append({"sido_code": u[0], "region": I["name"][u], "title": it["title"], "contentid": it["contentid"],
                    "kogl": it["cpyrhtDivCd"], "img": cp.KR_DIR / f"{it['contentid']}.jpg"})
    return v, out


def query_photo(place, v):
    """해외지 사진 중 평균 벡터와 가장 닮은 1장과 저작자 정보."""
    e = np.load(sc.EMB)
    names = [str(n) for n in e["names"]]
    cand = [i for i, n in enumerate(names) if n.split("__")[0] == place]
    i = max(cand, key=lambda k: float(e["vecs"][k] @ v))
    file = names[i]
    rows = sc.ok_rows().set_index("file")
    r = rows.loc[file]
    return {"path": sc.IMG_DIR / file, "scene": r.scene_label_ko, "artist": str(r.artist), "license": str(r.license),
            "license_url": str(r.license_url), "page": str(r.commons_page), "title": str(r.commons_title)}


# ------------------------------------------------------------------ 혼잡도 (P1 월 단위 ridge, 10장 명세 특징)
def monthly_forecast(target_month):
    import p1_spec as S
    wide = S.load_daily()
    A = wide.resample("MS").sum()
    a, months = A.values, list(A.index)
    t_star = len(months) + (pd.Period(target_month, "M") - pd.Period(months[-1], "M")).n - 1
    assert t_star - 2 == len(months) - 1, "예측 시점이 마지막 데이터의 2개월 뒤여야 한다"
    R = a.shape[1]

    def feats(t, yr, month):
        o = t - 2
        yoy = np.log((a[o] + a[o - 1] + a[o - 2] + 1) / (a[o - 12] + a[o - 13] + a[o - 14] + 1))
        a24 = a[t - 24] if t >= 24 else a[t - 12]
        oh = np.zeros((R, 12))
        oh[:, month - 1] = 1
        return np.column_stack([np.log1p(a[t - 12]), np.log1p(a[o]), np.log1p(a[o - 1]), yoy, np.log1p(a24),
                                np.full(R, int(yr in (2020, 2021))), np.full(R, int(yr - 1 in (2020, 2021))), oh])
    X, y = [], []
    for t in range(16, len(months)):  # 실측이 있는 모든 목표월로 학습
        X.append(feats(t, months[t].year, months[t].month))
        y.append(a[t])
    beta = S.ridge_fit(S.with_intercept(np.vstack(X)), np.log1p(np.concatenate(y)))
    tp = pd.Period(target_month, "M")
    pred = np.expm1(S.with_intercept(feats(t_star, tp.year, tp.month)) @ beta)
    recent = a[-12:].mean(0)
    return dict(zip(wide.columns, pred)), dict(zip(wide.columns, recent))


def visit_code_names():
    p = VISIT_RAW / "202512.json.gz"  # 2026-07 전남·광주 코드 변경 전 달 (p1_spec 은 구코드로 합쳐 둠)
    items = json.load(gzip.open(p, "rt", encoding="utf-8"))["response"]["body"]["items"]["item"]
    return {i["signguCode"]: i["signguNm"] for i in items}


def congestion_for(recs, pred, recent, code_names):
    """추천 시군구(TourAPI 단위)를 방문자수 코드에 이름으로 연결. 구가 있는 시는 구를 합친다."""
    by_key = {}
    for code in pred:
        nm = code_names.get(code, "")
        sido = VISIT_TO_TOUR_SIDO.get(code[:2], code[:2])
        by_key.setdefault((sido, nm.split()[0] if nm else ""), []).append(code)
    out = []
    for r in recs:
        codes = by_key.get((r["sido_code"], r["region"].split()[-1]), [])
        if not codes:
            out.append({**r, "pred": None, "index": None})
            continue
        pv, rc = sum(pred[c] for c in codes), sum(recent[c] for c in codes)
        out.append({**r, "pred": pv, "index": 100 * pv / rc})
    return out


# ------------------------------------------------------------------ HTML
def b64(path, max_side=900):
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))  # 비율 유지 축소만 (자르기·필터 없음)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def section_html(q, place_ko, rows, month_label):
    e = html.escape
    cards = "".join(f"""
      <li class="rec">
        <span class="rank">{k}</span>
        <figure><img src="{b64(r['img'])}" alt="{e(r['title'])}"></figure>
        <div class="meta">
          <strong>{e(r['title'])}</strong>
          <span>{e(r['region'])}</span>
          <small>{e(KOGL.get(r['kogl'], r['kogl']))} · 출처 한국관광공사</small>
        </div>
      </li>""" for k, r in enumerate(rows, 1))
    max_idx = max([r["index"] for r in rows if r["index"]] + [100])
    bars = "".join(f"""
      <div class="bar-row">
        <span class="bar-label">{e(r['region'].split()[-1])}</span>
        <div class="bar-track">{'' if r['index'] is None else f'<div class="bar" style="width:{min(100, r["index"] / max_idx * 100):.1f}%"></div><span class="ref" style="left:{100 / max_idx * 100:.1f}%"></span>'}</div>
        <span class="bar-val">{'데이터 없음' if r['index'] is None else f"{r['index']:.0f} · 약 {r['pred'] / 10000:.1f}만 명"}</span>
      </div>""" for r in rows)
    return f"""
  <section class="query">
    <div class="left">
      <h2>{e(place_ko)} <small>{e(q['scene'])}</small></h2>
      <figure class="qimg"><img src="{b64(q['path'])}" alt="{e(q['scene'])}"></figure>
      <p class="credit">사진: {e(q['artist'])} · <a href="{e(q['license_url'])}">{e(q['license'])}</a> ·
        <a href="{e(q['page'])}">Wikimedia Commons</a></p>
    </div>
    <div class="right">
      <h3>분위기가 비슷한 국내 시군구 상위 5</h3>
      <ol class="recs">{cards}
      </ol>
    </div>
    <div class="bottom">
      <h3>{e(month_label)} 혼잡도 예측 <small>최근 12개월 월평균 = 100 (세로선) · 외지인 방문자 수</small></h3>
      {bars}
    </div>
  </section>"""


CSS = """
:root{--bg:#f7f7f5;--fg:#1d1d1f;--muted:#6b6b70;--card:#fff;--line:#e3e3e0;--accent:#2f6f5e;--accent2:#c8ddd6}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececee;--muted:#a0a0a8;--card:#1f1f23;--line:#33333a;--accent:#7cc4ad;--accent2:#2e4a42}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 "Noto Sans KR","Malgun Gothic",system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px;margin-bottom:20px}
header h1{font-size:22px;margin:0}.badge{background:var(--accent);color:var(--bg);padding:2px 10px;border-radius:999px;font-size:13px;font-weight:600}
header p{margin:0;color:var(--muted);font-size:13px;flex-basis:100%}
.query{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,6fr);gap:20px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:24px}
.bottom{grid-column:1/-1}
h2{font-size:20px;margin:0 0 10px}h2 small,h3 small{color:var(--muted);font-weight:400;font-size:13px}h3{font-size:15px;margin:0 0 10px}
.qimg{margin:0;background:var(--bg);border-radius:10px;display:flex;align-items:center;justify-content:center;aspect-ratio:4/3}
.qimg img,.rec img{max-width:100%;max-height:100%;object-fit:contain;display:block}
.credit{font-size:12px;color:var(--muted);margin:8px 0 0}.credit a{color:var(--accent)}
.recs{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.rec{display:grid;grid-template-columns:28px 120px minmax(0,1fr);gap:12px;align-items:center}
.rank{font-weight:700;color:var(--accent);text-align:center}
.rec figure{margin:0;width:120px;height:84px;background:var(--bg);border-radius:8px;display:flex;align-items:center;justify-content:center}
.meta{display:flex;flex-direction:column;min-width:0}.meta strong{overflow-wrap:anywhere}.meta span{color:var(--muted);font-size:13px}.meta small{color:var(--muted);font-size:12px}
.bar-row{display:grid;grid-template-columns:90px minmax(0,1fr) 150px;gap:10px;align-items:center;margin:6px 0}
.bar-label{font-size:13px}.bar-val{font-size:13px;color:var(--muted)}
.bar-track{position:relative;height:16px;background:var(--bg);border-radius:4px}
.bar{height:100%;background:var(--accent);border-radius:4px}.ref{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--fg);opacity:.5}
footer{color:var(--muted);font-size:12px}
@media (max-width:760px){.query{grid-template-columns:1fr}.rec{grid-template-columns:24px 96px minmax(0,1fr)}.rec figure{width:96px;height:68px}.bar-row{grid-template-columns:70px minmax(0,1fr) 110px}}
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    I = sc.domestic_index()
    qv, by_scene = sc.scene_vectors()
    rows = sc.ok_rows()
    scenes_of = rows.groupby("place_id").scene_id.unique().to_dict()
    he = np.load(hp.HOLDOUT_EMB)
    extra = {}
    for v, pid in zip(he["vecs"], he["place_ids"]):
        extra.setdefault(str(pid), []).append(v)
    places_ko = pd.read_csv(sc.PLACES_CSV).set_index("place_id").name_ko.to_dict()
    pred, recent = monthly_forecast(TARGET_MONTH)
    code_names = visit_code_names()
    p = pd.Period(TARGET_MONTH, "M")
    month_label = f"{p.year}년 {p.month}월"

    sections = []
    for place in QUERIES:
        v, recs = recommend(I, place, qv, by_scene, scenes_of, extra)
        recs = congestion_for(recs, pred, recent, code_names)
        q = query_photo(place, v)
        sections.append(section_html(q, places_ko[place], recs, month_label))
        print(f"[{place}] " + " | ".join(f"{r['region']}·{r['title']}·{r['kogl']}·"
                                        f"{'없음' if r['index'] is None else round(r['index'])}" for r in recs))
    page = f"""<title>해외 닮은 국내 여행지 데모</title>
<style>{CSS}</style>
<div class="wrap">
  <header>
    <h1>해외 → 국내 분위기 유사 여행지</h1><span class="badge">{LABEL}</span>
    <p>해외 여행지 사진과 국내 관광지 사진을 CLIP으로 비교해 비슷한 시군구를 추천합니다.
       예시 질의는 평가 개발셋에서 골랐으며, 정답을 맞힌 결과가 아니라 화면 구성 확인용입니다.</p>
  </header>
  {''.join(sections)}
  <footer>추천: CLIP ViT-B/32, 시군구 vote100, TourAPI 대표사진 풀 · 혼잡도: 외지인 방문자 수 월 단위 ridge (HANDOFF 10-1 명세, 2026-08까지 실측으로 학습)
    · 국내 사진 출처 한국관광공사(공공누리) · 해외 사진 Wikimedia Commons (사진별 라이선스)</footer>
</div>
"""
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print(f"완료: {OUT / 'index.html'} ({(OUT / 'index.html').stat().st_size / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
