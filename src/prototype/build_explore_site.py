"""분위기 탐색 서비스 프로토타입 (로컬 확인용 정적 사이트).

해외 여행지(카탈로그 107곳)를 고르면 서비스 기본값(C, 시군구 vote100, 대표사진 풀)으로
분위기가 비슷한 국내 시군구 상위 10곳을 보여준다. 장면을 고르면 그 장면 기준 추천으로 바뀐다.
각 추천에는 그 시군구에서 가장 닮은 관광지 사진(공공누리 표기)과 2026년 10월 혼잡도(P1 월 단위)를 붙인다.

결과는 data/interim/web/ 에 만든다 (Git 제외). 사진은 data/interim/clip/ 파일을 심볼릭 링크로 연결한다.

실행:
    .venv/bin/python src/prototype/build_explore_site.py
    .venv/bin/python -m http.server 8000 --directory data/interim/web     # 브라우저에서 http://localhost:8000
    .venv/bin/python src/prototype/build_explore_site.py artifact <경로.html>  # 사진 내장 단일 파일 (claude.ai 아티팩트용)
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import clip_proto as cp
import holdout_pilot as hp
import make_demo_page as demo
import scene_catalog as sc

OUT = cp.WORK.parent / "web"
TOP_N = 10
HOLDOUT_CSV = cp.ROOT / "data/external/overseas_scenes_holdout_additions_20261002.csv"


def link(name, target):
    p = OUT / "img" / name
    if p.is_symlink() or p.exists():
        p.unlink()
    os.symlink(os.path.relpath(target, p.parent), p)


def photo_meta():
    """해외 사진 파일 → 장면·저작자 정보 (카탈로그 + 보강 사진)."""
    s = sc.ok_rows()
    rows = {r.file: {"src": f"img/scenes/{r.file}", "scene_id": r.scene_id, "scene": r.scene_label_ko,
                     "place": r.place_id, "artist": str(r.artist), "license": str(r.license),
                     "license_url": str(r.license_url), "page": str(r.commons_page)} for r in s.itertuples()}
    h = pd.read_csv(HOLDOUT_CSV)
    for r in h.itertuples():
        f = f"{r.scene_id}_{r.photo_rank}.jpg"
        rows[f] = {"src": f"img/holdout/{f}", "scene_id": r.scene_id, "scene": r.scene_label_ko, "place": r.place_id,
                   "artist": str(r.artist), "license": str(r.license), "license_url": str(r.license_url),
                   "page": str(r.commons_page)}
    return rows


def build_data():
    I = sc.domestic_index()
    meta = photo_meta()
    # 장면별 벡터: 카탈로그 + 보강 사진
    vecs = {}
    for name_file in [sc.EMB, hp.HOLDOUT_EMB]:
        e = np.load(name_file)
        for v, n in zip(e["vecs"], e["names"]):
            m = meta.get(str(n))
            if m:
                vecs.setdefault(m["scene_id"], []).append((v, str(n)))
    places = pd.read_csv(sc.PLACES_CSV).set_index("place_id")
    pred, recent = demo.monthly_forecast(demo.TARGET_MONTH)
    code_names = demo.visit_code_names()

    def recommend(v):
        v = v / np.linalg.norm(v)
        scores, sims, _ = sc.vote_scores(I, v)
        out = []
        for ri in np.argsort(-scores, kind="stable")[:TOP_N]:
            idx = np.where(I["img_region"] == ri)[0]
            best = idx[np.argmax(sims[idx])]
            it = I["items"][str(I["cid"][best])]
            u = I["regions"][ri]
            out.append({"sido_code": u[0], "region": I["name"][u], "title": it["title"],
                        "kogl": demo.KOGL.get(it["cpyrhtDivCd"], it["cpyrhtDivCd"]),
                        "img": f"img/kr/{it['contentid']}.jpg"})
        for r in demo.congestion_for(out, pred, recent, code_names):
            r.pop("sido_code")
            r["congestion"] = None if r["index"] is None else round(r["index"])
            r["visitors_10k"] = None if r["pred"] is None else round(r["pred"] / 10000, 1)
            r.pop("index"), r.pop("pred")
        return out

    data = []
    for pid, row in places.iterrows():
        scene_ids = sorted({sid for sid in vecs if sid.split("__")[0] == pid})
        if not scene_ids:
            continue
        all_v = [v for sid in scene_ids for v, _ in vecs[sid]]
        scenes = []
        for sid in scene_ids:
            files = [f for _, f in vecs[sid]]
            scenes.append({"id": sid, "label": meta[files[0]]["scene"],
                           "photos": [{k: meta[f][k] for k in ("src", "artist", "license", "license_url", "page")}
                                      for f in files],
                           "recs": recommend(np.mean([v for v, _ in vecs[sid]], 0))})
        data.append({"id": pid, "name": row.name_ko, "name_en": row.name_en, "country": row.country_code,
                     "tags": [t for t in str(row.vibe_tags).split(",") if t and t != "nan"],
                     "recs": recommend(np.mean(all_v, 0)), "scenes": scenes})
    p = pd.Period(demo.TARGET_MONTH, "M")
    return {"month": f"{p.year}년 {p.month}월", "places": data}


def write_site():
    """로컬 서버용: data.js + index.html, 사진은 심볼릭 링크."""
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    link("kr", cp.KR_DIR)
    link("scenes", sc.IMG_DIR)
    link("holdout", cp.WORK / "scenes_holdout")
    data = build_data()
    (OUT / "data.js").write_text("window.DATA = " + json.dumps(data, ensure_ascii=False) + ";", encoding="utf-8")
    (OUT / "index.html").write_text(PAGE, encoding="utf-8")
    print(f"완료: 해외 {len(data['places'])}곳 → {OUT}")


def write_artifact(path, kr_side=200, scene_side=300, quality=65):
    """단일 파일용: 사진을 비율 유지 축소(자르기 없음) 후 base64 로 한 번씩만 넣는다."""
    import base64
    import io
    from PIL import Image
    data = build_data()
    files = {"img/kr": cp.KR_DIR, "img/scenes": sc.IMG_DIR, "img/holdout": cp.WORK / "scenes_holdout"}
    pool = {}

    def ref(src):
        if src not in pool:
            folder, name = src.rsplit("/", 1)
            side = kr_side if folder == "img/kr" else scene_side
            im = Image.open(files[folder] / name).convert("RGB")
            im.thumbnail((side, side))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality)
            pool[src] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        return src

    for pl in data["places"]:
        for r in pl["recs"]:
            ref(r["img"])
        for x in pl["scenes"]:
            ref(x["photos"][0]["src"])  # 화면에는 장면당 첫 사진만 쓴다 (저작자 표기는 전부 유지)
            for r in x["recs"]:
                ref(r["img"])
    data["img"] = pool
    page = ARTIFACT_PAGE.replace("/*DATA*/", "window.DATA = " + json.dumps(data, ensure_ascii=False) + ";")
    Path(path).write_text(page, encoding="utf-8")
    print(f"완료: 해외 {len(data['places'])}곳, 사진 {len(pool)}장, {Path(path).stat().st_size / 1e6:.1f}MB → {path}")


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>닮은 국내 여행지 탐색</title>
<style>
:root{--bg:#f6f6f3;--fg:#1c1c1e;--muted:#6b6b70;--card:#fff;--line:#e2e2de;--accent:#2f6f5e;--soft:#e7f0ec}
@media (prefers-color-scheme:dark){:root{--bg:#131315;--fg:#ececee;--muted:#a0a0a8;--card:#1d1d21;--line:#313137;--accent:#7cc4ad;--soft:#22322d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 "Noto Sans KR","Malgun Gothic",system-ui,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 20px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline}
header h1{font-size:19px;margin:0}.badge{background:var(--accent);color:var(--bg);border-radius:999px;padding:1px 10px;font-size:12px;font-weight:600}
header p{margin:0;color:var(--muted);font-size:13px}
.layout{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:calc(100vh - 56px)}
aside{border-right:1px solid var(--line);padding:14px;position:sticky;top:56px;height:calc(100vh - 56px);overflow:auto}
aside input{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font:inherit}
.plist{list-style:none;margin:10px 0 0;padding:0}.plist li{padding:7px 10px;border-radius:8px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
.plist li:hover{background:var(--soft)}.plist li.on{background:var(--accent);color:var(--bg)}.plist small{opacity:.7}
main{padding:20px;min-width:0}
.head h2{margin:0;font-size:24px}.head .tags span{display:inline-block;background:var(--soft);color:var(--accent);border-radius:999px;padding:0 9px;margin:4px 4px 0 0;font-size:12px}
.scenes{display:flex;gap:10px;overflow-x:auto;padding:12px 0}
.scene{flex:0 0 auto;width:170px;border:2px solid transparent;border-radius:10px;background:var(--card);cursor:pointer;padding:6px}
.scene.on{border-color:var(--accent)}.scene .ph{height:110px;display:flex;align-items:center;justify-content:center;background:var(--bg);border-radius:6px}
.scene img{max-width:100%;max-height:100%;object-fit:contain}.scene div.l{font-size:13px;margin-top:4px}
.credit{font-size:12px;color:var(--muted);margin:2px 0 14px}.credit a{color:var(--accent)}
.mode{font-size:13px;color:var(--muted);margin:4px 0 10px}.mode b{color:var(--fg)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.card .ph{height:160px;background:var(--bg);display:flex;align-items:center;justify-content:center;position:relative}
.card .ph img{max-width:100%;max-height:100%;object-fit:contain}
.card .rk{position:absolute;top:8px;left:8px;background:var(--accent);color:var(--bg);font-weight:700;border-radius:999px;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-size:13px}
.card .bd{padding:10px 12px 12px;display:flex;flex-direction:column;gap:2px}
.card .rg{font-weight:700}.card .tt{font-size:13px}.card .kg{font-size:11px;color:var(--muted)}
.cg{margin-top:6px;font-size:12px;color:var(--muted)}.bar{height:7px;background:var(--bg);border-radius:4px;position:relative;margin-top:3px}
.bar i{position:absolute;inset:0 auto 0 0;background:var(--accent);border-radius:4px}.bar u{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--fg);opacity:.45}
footer{color:var(--muted);font-size:12px;padding:20px 0 0}
@media (max-width:760px){.layout{grid-template-columns:1fr}aside{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}.plist{max-height:200px;overflow:auto}}
</style>
<script src="data.js"></script></head>
<body>
<header><h1>해외 여행지와 분위기가 닮은 국내 여행지</h1><span class="badge">프로토타입</span>
<p>사진(CLIP)으로 비교한 탐색용 추천입니다. 정확도는 검증 중이며, 근거 사진을 보고 직접 판단해 주세요.</p></header>
<div class="layout">
<aside><input id="q" placeholder="여행지 검색 (예: 교토, 스위스)"><ul class="plist" id="plist"></ul></aside>
<main id="main"></main>
</div>
<script>
const D = window.DATA, $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let cur = null, scene = null;
function list(filter = "") {
  const f = filter.trim().toLowerCase();
  $("#plist").innerHTML = D.places.filter(p => !f || (p.name + p.name_en + p.tags.join()).toLowerCase().includes(f))
    .map(p => `<li data-id="${p.id}" class="${cur && cur.id === p.id ? "on" : ""}">${esc(p.name)}<small>${esc(p.country)}</small></li>`).join("");
}
function cards(recs) {
  const max = Math.max(100, ...recs.map(r => r.congestion || 0));
  return recs.map((r, i) => `
    <article class="card"><div class="ph"><span class="rk">${i + 1}</span><img loading="lazy" src="${r.img}" alt="${esc(r.title)}"></div>
    <div class="bd"><span class="rg">${esc(r.region)}</span><span class="tt">가장 닮은 관광지: ${esc(r.title)}</span>
    <span class="kg">${esc(r.kogl)} · 출처 한국관광공사</span>
    <div class="cg">${r.congestion == null ? "혼잡도 데이터 없음" : `${D.month} 혼잡도 ${r.congestion} (평소=100) · 외지인 약 ${r.visitors_10k}만 명`}
    ${r.congestion == null ? "" : `<div class="bar"><i style="width:${Math.min(100, r.congestion / max * 100)}%"></i><u style="left:${100 / max * 100}%"></u></div>`}</div></div></article>`).join("");
}
function show(p, s = null) {
  cur = p; scene = s; list($("#q").value);
  const photo = (s || p.scenes[0]).photos[0];
  $("#main").innerHTML = `
    <div class="head"><h2>${esc(p.name)} <small style="font-size:14px;color:var(--muted)">${esc(p.name_en)}</small></h2>
    <div class="tags">${p.tags.map(t => `<span>${esc(t)}</span>`).join("")}</div></div>
    <div class="scenes">${p.scenes.map(x => `<div class="scene ${s && s.id === x.id ? "on" : ""}" data-s="${x.id}">
      <div class="ph"><img loading="lazy" src="${x.photos[0].src}" alt="${esc(x.label)}"></div><div class="l">${esc(x.label)}</div></div>`).join("")}</div>
    <p class="credit">${(s ? s.photos : p.scenes.flatMap(x => x.photos)).map(f => `${esc(f.artist)} · <a href="${esc(f.license_url)}" target="_blank" rel="noopener">${esc(f.license)}</a> · <a href="${esc(f.page)}" target="_blank" rel="noopener">Commons</a>`).join(" / ")}</p>
    <p class="mode">${s ? `<b>장면 "${esc(s.label)}"</b> 기준 추천 · <a href="#" id="all">여행지 전체로 보기</a>` : `<b>여행지 전체 사진</b> 기준 추천 · 장면을 누르면 그 장면 기준으로 바뀝니다`}</p>
    <section class="grid">${cards(s ? s.recs : p.recs)}</section>
    <footer>추천: CLIP ViT-B/32 · 시군구 vote100 · TourAPI 대표사진 · 혼잡도: 외지인 방문자 월 단위 예측(${D.month}) · 프로토타입</footer>`;
  document.querySelectorAll(".scene").forEach(el => el.onclick = () => show(p, p.scenes.find(x => x.id === el.dataset.s)));
  const a = $("#all"); if (a) a.onclick = e => { e.preventDefault(); show(p); };
}
$("#plist").onclick = e => { const li = e.target.closest("li"); if (li) show(D.places.find(p => p.id === li.dataset.id)); };
$("#q").oninput = e => list(e.target.value);
list(); show(D.places.find(p => p.id === "kyoto") || D.places[0]);
</script></body></html>
"""

ARTIFACT_PAGE = r"""<title>닮은꼴 국내 여행지</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600&family=Nanum+Myeongjo:wght@700;800&display=swap">
<style>
/* 레이아웃: 왼쪽 여행지 목록(고정) + 오른쪽 장면 띠 → 추천 카드 격자. 엽서 같은 여행지명, 조용한 도구 UI */
:root{
  --paper:#f4f5f1; --surface:#ffffff; --ink:#1b2420; --sub:#5d6862; --rule:#dde2dc;
  --pine:#2c6a57; --pine-soft:#e3eee8; --on-pine:#ffffff; --busy:#b5562f;
  --f-display:"Nanum Myeongjo","Noto Serif KR",serif;
  --f-body:"IBM Plex Sans KR","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;
  --gut:clamp(16px,3vw,28px);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#121614; --surface:#1a201d; --ink:#e7ece9; --sub:#9aa6a0; --rule:#2c3531;
  --pine:#7cc2a8; --pine-soft:#1f302a; --on-pine:#0f1412; --busy:#e08a63; color-scheme:dark}}
:root[data-theme="dark"]{
  --paper:#121614; --surface:#1a201d; --ink:#e7ece9; --sub:#9aa6a0; --rule:#2c3531;
  --pine:#7cc2a8; --pine-soft:#1f302a; --on-pine:#0f1412; --busy:#e08a63; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font:15px/1.6 var(--f-body)}
a{color:var(--pine)}
:focus-visible{outline:2px solid var(--pine);outline-offset:2px}
.top{position:sticky;top:env(safe-area-inset-top,0px);z-index:3;background:var(--paper);border-bottom:1px solid var(--rule);
  padding:12px var(--gut);display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 14px}
.top h1{margin:0;font:800 20px/1.3 var(--f-display);text-wrap:balance}
.pill{background:var(--pine);color:var(--on-pine);border-radius:999px;padding:1px 10px;font-size:12px;font-weight:600;letter-spacing:.02em}
.top p{margin:0;color:var(--sub);font-size:13px;flex-basis:100%;max-width:70ch}
.layout{display:grid;grid-template-columns:240px minmax(0,1fr)}
aside{border-right:1px solid var(--rule);padding:16px 12px 16px var(--gut);position:sticky;top:96px;align-self:start;max-height:calc(100vh - 110px);overflow:auto}
#q{width:100%;padding:8px 10px;border:1px solid var(--rule);border-radius:8px;background:var(--surface);color:var(--ink);font:inherit}
.plist{list-style:none;margin:10px 0 0;padding:0;display:flex;flex-direction:column;gap:2px}
.plist button{all:unset;box-sizing:border-box;width:100%;padding:6px 10px;border-radius:8px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
.plist button:hover{background:var(--pine-soft)}
.plist button[aria-current="true"]{background:var(--pine);color:var(--on-pine)}
.plist small{opacity:.65;font-variant-numeric:tabular-nums}
main{padding:20px var(--gut) 40px;min-width:0;display:flex;flex-direction:column;gap:14px}
.head{display:flex;flex-direction:column;gap:6px}
.head h2{margin:0;font:800 30px/1.2 var(--f-display);text-wrap:balance}
.head h2 small{font:400 14px var(--f-body);color:var(--sub);margin-left:8px}
.tags{display:flex;flex-wrap:wrap;gap:6px}.tags span{background:var(--pine-soft);color:var(--pine);border-radius:999px;padding:0 10px;font-size:12px}
.scenes{display:flex;gap:10px;overflow-x:auto;padding-bottom:4px}
.scene{all:unset;box-sizing:border-box;flex:0 0 auto;width:168px;border:2px solid var(--rule);border-radius:10px;background:var(--surface);cursor:pointer;padding:6px;display:flex;flex-direction:column;gap:4px}
.scene[aria-pressed="true"]{border-color:var(--pine)}
.scene .ph{height:104px;display:flex;align-items:center;justify-content:center;background:var(--paper);border-radius:6px}
.scene img{max-width:100%;max-height:100%;object-fit:contain;display:block}
.scene span{font-size:13px}
.credit{font-size:12px;color:var(--sub);margin:0}
.mode{font-size:13px;color:var(--sub);margin:0}.mode b{color:var(--ink);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.card .ph{height:150px;background:var(--paper);display:flex;align-items:center;justify-content:center;position:relative}
.card .ph img{max-width:100%;max-height:100%;object-fit:contain;display:block}
.rk{position:absolute;top:8px;left:8px;background:var(--pine);color:var(--on-pine);font-weight:600;border-radius:999px;min-width:26px;height:26px;padding:0 6px;
  display:flex;align-items:center;justify-content:center;font-size:13px;font-variant-numeric:tabular-nums}
.bd{padding:10px 12px 12px;display:flex;flex-direction:column;gap:2px}
.rg{font-weight:600}.rg small{color:var(--sub);font-weight:400;margin-left:4px;font-size:12px}
.tt{font-size:13px}.kg{font-size:11px;color:var(--sub)}
.cg{margin-top:8px;font-size:12px;color:var(--sub);font-variant-numeric:tabular-nums}
.bar{height:6px;background:var(--paper);border-radius:3px;position:relative;margin-top:4px}
.bar i{position:absolute;inset:0 auto 0 0;background:var(--pine);border-radius:3px}
.bar i.hi{background:var(--busy)}
.bar u{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink);opacity:.4}
footer{color:var(--sub);font-size:12px;max-width:90ch}
@media (max-width:760px){
  .layout{grid-template-columns:1fr}
  aside{position:static;max-height:none;border-right:0;border-bottom:1px solid var(--rule);padding:12px var(--gut)}
  .plist{flex-direction:row;overflow-x:auto;gap:6px}.plist button{white-space:nowrap;width:auto;border:1px solid var(--rule)}
  .head h2{font-size:24px}
}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
</style>
<header class="top"><h1>해외 여행지와 분위기가 닮은 국내 여행지</h1><span class="pill">프로토타입</span>
<p>해외 여행지 사진과 국내 관광지 사진을 비교해 비슷한 시군구를 찾아 줍니다. 탐색용 추천이고 정확도는 검증 중이니, 근거 사진을 보고 판단해 주세요.</p></header>
<div class="layout">
<aside><label for="q" class="credit">여행지 검색</label><input id="q" placeholder="예: 교토, 스위스, 해변"><ul class="plist" id="plist"></ul></aside>
<main id="main"></main>
</div>
<script>/*DATA*/</script>
<script>
const D = window.DATA, $ = s => document.querySelector(s), IMG = src => D.img[src] || "";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let cur = null;
function list() {
  const f = $("#q").value.trim().toLowerCase();
  $("#plist").innerHTML = D.places.filter(p => !f || (p.name + " " + p.name_en + " " + p.tags.join(" ")).toLowerCase().includes(f))
    .map(p => `<li><button type="button" data-id="${p.id}" aria-current="${cur && cur.id === p.id}">${esc(p.name)}<small>${esc(p.country)}</small></button></li>`).join("")
    || `<li class="credit">"${esc(f)}"에 맞는 여행지가 없습니다. 나라 이름이나 분위기(해변, 설산)로 찾아보세요.</li>`;
}
function cards(recs) {
  const max = Math.max(120, ...recs.map(r => r.congestion || 0));
  return recs.map((r, i) => {
    const parts = r.region.split(" "), sgg = parts.pop(), sido = parts.join(" ");
    const cg = r.congestion == null ? `<div class="cg">혼잡도 자료 없음</div>` :
      `<div class="cg">${D.month} 혼잡도 ${r.congestion} <span>(평소 100)</span> · 외지인 약 ${r.visitors_10k}만 명
       <div class="bar" role="img" aria-label="평소 대비 ${r.congestion}"><i class="${r.congestion >= 130 ? "hi" : ""}" style="width:${Math.min(100, r.congestion / max * 100)}%"></i><u style="left:${100 / max * 100}%"></u></div></div>`;
    return `<article class="card"><div class="ph"><span class="rk">${i + 1}</span><img src="${IMG(r.img)}" alt="${esc(r.title)}"></div>
      <div class="bd"><span class="rg">${esc(sgg)}<small>${esc(sido)}</small></span>
      <span class="tt">가장 닮은 관광지 · ${esc(r.title)}</span><span class="kg">${esc(r.kogl)} · 한국관광공사</span>${cg}</div></article>`;
  }).join("");
}
function show(p, s = null) {
  cur = p; list();
  const photos = s ? s.photos : p.scenes.flatMap(x => x.photos);
  $("#main").innerHTML = `
    <div class="head"><h2>${esc(p.name)}<small>${esc(p.name_en)}</small></h2>
      <div class="tags">${p.tags.map(t => `<span>${esc(t)}</span>`).join("")}</div></div>
    <div class="scenes">${p.scenes.map(x => `<button type="button" class="scene" data-s="${x.id}" aria-pressed="${!!(s && s.id === x.id)}">
      <div class="ph"><img src="${IMG(x.photos[0].src)}" alt="${esc(x.label)}"></div><span>${esc(x.label)}</span></button>`).join("")}</div>
    <p class="credit">해외 사진 · ${photos.map(f => `${esc(f.artist)}, <a href="${esc(f.license_url)}" target="_blank" rel="noopener">${esc(f.license)}</a>, <a href="${esc(f.page)}" target="_blank" rel="noopener">Wikimedia Commons</a>`).join(" / ")}</p>
    <p class="mode">${s ? `<b>장면 “${esc(s.label)}”</b> 기준으로 추천했습니다. <a href="#" id="all">여행지 전체 사진 기준으로 보기</a>`
                        : `<b>여행지 전체 사진</b> 기준으로 추천했습니다. 장면을 누르면 그 장면 기준으로 바뀝니다.`}</p>
    <section class="grid" aria-label="추천 시군구">${cards(s ? s.recs : p.recs)}</section>
    <footer>추천: CLIP ViT-B/32 이미지 임베딩, 시군구 단위 vote100, 한국관광공사 대표사진 · 혼잡도: 외지인 방문자 월 단위 예측(${D.month}, 최근 12개월 평균 = 100) · 사진은 비율을 유지해 축소만 했습니다.</footer>`;
  document.querySelectorAll(".scene").forEach(el => el.onclick = () => show(p, p.scenes.find(x => x.id === el.dataset.s)));
  const a = $("#all"); if (a) a.onclick = e => { e.preventDefault(); show(p); };
}
$("#plist").onclick = e => { const b = e.target.closest("button"); if (b) show(D.places.find(p => p.id === b.dataset.id)); };
$("#q").oninput = list;
show(D.places.find(p => p.id === "kyoto") || D.places[0]);
</script>
"""


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "artifact":
        write_artifact(sys.argv[2])
    else:
        write_site()
