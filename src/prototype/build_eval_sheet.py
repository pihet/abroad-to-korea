"""사람 평가 시트: 해외 여행지 30곳의 추천 상위 5곳을 팀원이 '그럴듯함 / 애매함 / 엉뚱함'으로 판정한다.

- 대상: 수요 상위(demand_agoda2025) 10곳 전부 + 나머지 카탈로그에서 무작위 20곳 (seed 42, 정답 쌍과 무관)
- 추천: 서비스 기본값 (CLIP ViT-B/32, 시군구 vote100, 대표사진 풀) 상위 5곳
- 순위 번호는 숨기고 해외지마다 고정 난수로 순서를 섞는다 (순위 선입견 방지)
- 판정 저장: 아티팩트 db 의 ratings/<평가자 id>/items/<해외지__순위> + 평가자 문서 ratings/<평가자 id>. 평가자는 자기 판정만 보고,
  소유자는 전체를 읽는다 (db rules). Claude 는 Artifact read_db 로 집계한다.

실행: .venv/bin/python src/prototype/build_eval_sheet.py <출력 경로.html>
"""

import json
import random
import sys
from pathlib import Path

import pandas as pd

import build_explore_site as ex
import scene_catalog as sc

N_RANDOM = 20
SEED = 42
TOP = 5

DB_RULES = [  # 평가자는 자기 판정만 쓰고 읽는다, 소유자는 전부 읽는다
    {"path": "ratings", "read": "owner", "write": "owner"},
    {"path": "ratings/{self}", "write": "interact"},
]


def pick_places(data):
    places = pd.read_csv(sc.PLACES_CSV).set_index("place_id")
    have = {p["id"] for p in data["places"]}
    demand = [p for p in places.index if "demand_agoda2025" in str(places.loc[p, "selection_reason"]) and p in have]
    rest = sorted(have - set(demand))
    rng = random.Random(SEED)
    return demand + sorted(rng.sample(rest, N_RANDOM))


def main(out):
    data = ex.build_data()
    chosen = pick_places(data)
    by_id = {p["id"]: p for p in data["places"]}
    rng = random.Random(SEED)
    items, pool = [], {}

    def ref(src, side):
        key = src
        if key not in pool:
            import base64, io
            from PIL import Image
            folder, name = src.rsplit("/", 1)
            base = {"img/kr": ex.cp.KR_DIR, "img/scenes": sc.IMG_DIR, "img/holdout": ex.cp.WORK / "scenes_holdout"}[folder]
            im = Image.open(base / name).convert("RGB")
            im.thumbnail((side, side))  # 비율 유지 축소만
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=72)
            pool[key] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        return key

    for pid in chosen:
        p = by_id[pid]
        photos = [x["photos"][0] for x in p["scenes"]][:3]
        recs = [{"key": f"{pid}__{k + 1}", "region": r["region"], "title": r["title"], "kogl": r["kogl"],
                 "img": ref(r["img"], 320)} for k, r in enumerate(p["recs"][:TOP])]
        rng.shuffle(recs)  # 순위 숨김
        items.append({"id": pid, "name": p["name"], "name_en": p["name_en"], "tags": p["tags"],
                      "photos": [{"img": ref(f["src"], 420), "credit": f"{f['artist']} · {f['license']}",
                                  "page": f["page"]} for f in photos],
                      "recs": recs})
    page = PAGE.replace("/*DATA*/", "window.EVAL = " + json.dumps({"places": items, "img": pool}, ensure_ascii=False) + ";")
    Path(out).write_text(page, encoding="utf-8")
    print(f"완료: 해외 {len(items)}곳 × {TOP} = {len(items) * TOP}건, 사진 {len(pool)}장, "
          f"{Path(out).stat().st_size / 1e6:.1f}MB → {out}")
    print("대상:", ", ".join(p["name"] for p in items))


PAGE = r"""<title>닮은꼴 추천 평가</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600&family=Nanum+Myeongjo:wght@800&display=swap">
<style>
/* 레이아웃: 위 안내·진행률, 해외지마다 한 블록(해외 사진 띠 → 국내 후보 5장 + 판정 버튼). 판정 상태는 색과 글자로 함께 표시 */
:root{
  --paper:#f4f5f1; --surface:#ffffff; --ink:#1b2420; --sub:#5d6862; --rule:#dde2dc;
  --pine:#2c6a57; --pine-soft:#e3eee8; --on-pine:#ffffff;
  --ok:#2c6a57; --ok-soft:#e3eee8; --meh:#9a6b12; --meh-soft:#f6ecd6; --bad:#b0412a; --bad-soft:#f6e1da;
  --f-display:"Nanum Myeongjo","Noto Serif KR",serif;
  --f-body:"IBM Plex Sans KR","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;
  --gut:clamp(16px,3vw,28px);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#121614; --surface:#1a201d; --ink:#e7ece9; --sub:#9aa6a0; --rule:#2c3531; --pine:#7cc2a8; --pine-soft:#1f302a; --on-pine:#0f1412;
  --ok:#7cc2a8; --ok-soft:#1f302a; --meh:#e0b45c; --meh-soft:#352c19; --bad:#ec8a72; --bad-soft:#3a221c; color-scheme:dark}}
:root[data-theme="dark"]{
  --paper:#121614; --surface:#1a201d; --ink:#e7ece9; --sub:#9aa6a0; --rule:#2c3531; --pine:#7cc2a8; --pine-soft:#1f302a; --on-pine:#0f1412;
  --ok:#7cc2a8; --ok-soft:#1f302a; --meh:#e0b45c; --meh-soft:#352c19; --bad:#ec8a72; --bad-soft:#3a221c; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font:15px/1.6 var(--f-body)}
a{color:var(--pine)}:focus-visible{outline:2px solid var(--pine);outline-offset:2px}
.wrap{max-width:1180px;margin:0 auto;padding-inline:var(--gut);padding-block:20px 48px;display:flex;flex-direction:column;gap:22px}
.top{position:sticky;top:env(safe-area-inset-top,0px);z-index:3;background:var(--paper);border-bottom:1px solid var(--rule);padding:10px var(--gut);
  display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center}
.top h1{margin:0;font:800 19px/1.3 var(--f-display)}
.prog{font-variant-numeric:tabular-nums;font-size:14px}.prog b{color:var(--pine)}
.meter{flex:1 1 160px;height:8px;background:var(--rule);border-radius:4px;overflow:hidden;max-width:320px}.meter i{display:block;height:100%;background:var(--pine)}
.status{font-size:13px;color:var(--sub)}
.guide{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:16px 18px;display:grid;gap:8px;max-width:80ch}
.guide h2{margin:0;font-size:16px}.guide p,.guide ul{margin:0}.guide ul{padding-left:20px}
.chip{display:inline-block;border-radius:999px;padding:0 9px;font-size:12px;font-weight:600}
.chip.ok{background:var(--ok-soft);color:var(--ok)}.chip.meh{background:var(--meh-soft);color:var(--meh)}.chip.bad{background:var(--bad-soft);color:var(--bad)}
.place{display:grid;gap:12px;border-top:1px solid var(--rule);padding-top:20px}
.place header{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 12px}
.place h2{margin:0;font:800 26px/1.2 var(--f-display)}.place header small{color:var(--sub)}
.done{font-size:12px;color:var(--sub);font-variant-numeric:tabular-nums;margin-left:auto}
.strip{display:flex;gap:10px;overflow-x:auto}
.strip figure{margin:0;flex:0 0 auto;width:260px;display:flex;flex-direction:column;gap:4px}
.strip .ph{height:180px;background:var(--surface);border-radius:8px;display:flex;align-items:center;justify-content:center}
.strip img,.rec img{max-width:100%;max-height:100%;object-fit:contain;display:block}
.strip figcaption{font-size:11px;color:var(--sub)}
.recs{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.rec{background:var(--surface);border:2px solid var(--rule);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.rec[data-v="ok"]{border-color:var(--ok)}.rec[data-v="meh"]{border-color:var(--meh)}.rec[data-v="bad"]{border-color:var(--bad)}
.rec .ph{height:140px;background:var(--paper);display:flex;align-items:center;justify-content:center}
.rec .bd{padding:8px 10px 10px;display:flex;flex-direction:column;gap:2px;flex:1}
.rec .rg{font-weight:600}.rec .tt{font-size:13px}.rec .kg{font-size:11px;color:var(--sub)}
.btns{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-top:8px}
.btns button{font:inherit;font-size:13px;padding:6px 0;border-radius:8px;border:1px solid var(--rule);background:var(--paper);color:var(--ink);cursor:pointer}
.btns button[aria-pressed="true"][data-v="ok"]{background:var(--ok);border-color:var(--ok);color:var(--on-pine)}
.btns button[aria-pressed="true"][data-v="meh"]{background:var(--meh);border-color:var(--meh);color:var(--surface)}
.btns button[aria-pressed="true"][data-v="bad"]{background:var(--bad);border-color:var(--bad);color:var(--surface)}
.btns button:disabled{cursor:not-allowed;opacity:.5}
.owner{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:16px 18px;display:grid;gap:10px}
.owner h2{margin:0;font-size:16px}.owner table{border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
.owner td,.owner th{padding:4px 10px;border-bottom:1px solid var(--rule);text-align:right}.owner th:first-child,.owner td:first-child{text-align:left}
.tbl{overflow-x:auto}
.owner button{justify-self:start;font:inherit;padding:6px 14px;border-radius:8px;border:1px solid var(--pine);background:var(--pine);color:var(--on-pine);cursor:pointer}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
<div class="top"><h1>닮은꼴 추천 평가</h1><span class="prog" id="prog">판정 0 / 0</span><span class="meter"><i id="meter" style="width:0"></i></span><span class="status" id="status">불러오는 중</span></div>
<div class="wrap">
  <section class="guide">
    <h2>평가 방법</h2>
    <p>해외 여행지마다 국내 후보 5곳이 나옵니다. 순위는 숨기고 순서를 섞었습니다. 해외 사진과 국내 관광지 사진을 보고, 그 시군구가 <b>비슷한 분위기의 여행 대안</b>으로 그럴듯한지 판정해 주세요.</p>
    <ul>
      <li><span class="chip ok">그럴듯함</span> 이 해외 여행지 대신 가 볼 만하다고 납득된다</li>
      <li><span class="chip meh">애매함</span> 일부는 닮았지만 대안이라고 하기엔 약하다</li>
      <li><span class="chip bad">엉뚱함</span> 분위기가 전혀 다르다. 추천에 나오면 이상하다</li>
    </ul>
    <p>누르는 즉시 저장되고, 다시 누르면 바꿀 수 있습니다. 다른 사람의 판정은 보이지 않습니다. 해외지 하나에 1분 정도면 됩니다.</p>
  </section>
  <section class="owner" id="owner" hidden><h2>전체 결과 (소유자만 보임)</h2><p class="status">평가자들의 판정을 모아 봅니다.</p>
    <button type="button" id="load">결과 불러오기</button><div class="tbl" id="ownerOut"></div></section>
  <div id="list"></div>
</div>
<script>/*DATA*/</script>
<script>
const E = window.EVAL, $ = s => document.querySelector(s), IMG = k => E.img[k] || "";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const LABEL = {ok: "그럴듯함", meh: "애매함", bad: "엉뚱함"};
const TOTAL = E.places.reduce((n, p) => n + p.recs.length, 0);
let mine = {}, db = null, uid = null, writable = false;

function render() {
  $("#list").innerHTML = E.places.map(p => {
    const n = p.recs.filter(r => mine[r.key]).length;
    return `<section class="place" id="p-${p.id}"><header><h2>${esc(p.name)}</h2><small>${esc(p.name_en)} · ${p.tags.map(esc).join(", ")}</small>
      <span class="done">${n} / ${p.recs.length} 판정</span></header>
      <div class="strip">${p.photos.map(f => `<figure><div class="ph"><img src="${IMG(f.img)}" alt="${esc(p.name)} 사진"></div>
        <figcaption>${esc(f.credit)} · <a href="${esc(f.page)}" target="_blank" rel="noopener">Wikimedia Commons</a></figcaption></figure>`).join("")}</div>
      <div class="recs">${p.recs.map(r => `<article class="rec" data-v="${mine[r.key] || ""}"><div class="ph"><img src="${IMG(r.img)}" alt="${esc(r.title)}"></div>
        <div class="bd"><span class="rg">${esc(r.region)}</span><span class="tt">${esc(r.title)}</span><span class="kg">${esc(r.kogl)} · 한국관광공사</span>
        <div class="btns" role="group" aria-label="${esc(r.region)} 판정">${["ok","meh","bad"].map(v =>
          `<button type="button" data-k="${r.key}" data-v="${v}" aria-pressed="${mine[r.key] === v}" ${writable ? "" : "disabled"}>${LABEL[v]}</button>`).join("")}</div></div></article>`).join("")}</div>
    </section>`;
  }).join("");
  const done = Object.keys(mine).length;
  $("#prog").innerHTML = `판정 <b>${done}</b> / ${TOTAL}`;
  $("#meter").style.width = (done / TOTAL * 100) + "%";
}

$("#list").addEventListener("click", async e => {
  const b = e.target.closest("button[data-k]");
  if (!b || !writable) return;
  const key = b.dataset.k, v = b.dataset.v, [place, rank] = key.split("__");
  const prev = mine[key];
  mine = {...mine, [key]: v};
  render();
  try {
    await db.doc(`ratings/${uid}/items/${key}`).set({v, place, rank: Number(rank), ts: Date.now()});
    await markRater();
    $("#status").textContent = "저장됨";
  } catch (err) {
    mine = {...mine}; if (prev) mine[key] = prev; else delete mine[key];
    render();
    $("#status").textContent = err && err.code === "invalid_argument"
      ? "저장 권한이 없습니다. 소유자에게 Contributor 이상으로 공유해 달라고 요청하세요."
      : "저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요.";
  }
});

// 평가자 문서: 소유자 화면과 Claude 집계가 평가자 목록을 찾는 입구 (판정 항목은 그 아래 items 에 있다)
let raterMarked = false;
async function markRater() {
  if (raterMarked || !writable) return;
  await db.doc(`ratings/${uid}`).set({ts: Date.now()});
  raterMarked = true;
}

async function ownerSummary() {
  $("#ownerOut").textContent = "불러오는 중";
  const raters = await db.collection("ratings").get();
  const ids = new Set(raters.docs.map(d => d.id));
  // 평가자 문서가 없을 수 있으므로 판정 항목을 직접 읽는다
  const all = [];
  for (const id of ids) {
    const s = await db.collection(`ratings/${id}/items`).get();
    s.docs.forEach(d => all.push({rater: id, ...d.data()}));
  }
  if (!all.length) { $("#ownerOut").textContent = "아직 판정이 없습니다. 팀원에게 Contributor 권한으로 공유한 뒤 평가를 부탁하세요."; return; }
  const raterIds = [...new Set(all.map(x => x.rater))];
  const cnt = arr => ({ok: arr.filter(x => x.v === "ok").length, meh: arr.filter(x => x.v === "meh").length, bad: arr.filter(x => x.v === "bad").length, n: arr.length});
  const pct = (a, b) => b ? Math.round(a / b * 100) + "%" : "–";
  const t = cnt(all);
  const rows = E.places.map(p => { const c = cnt(all.filter(x => x.place === p.id)); return `<tr><td>${esc(p.name)}</td><td>${c.n}</td><td>${pct(c.ok, c.n)}</td><td>${pct(c.meh, c.n)}</td><td>${pct(c.bad, c.n)}</td></tr>`; }).join("");
  $("#ownerOut").innerHTML = `<p>평가자 ${raterIds.length}명 · 판정 ${t.n}건 · <span class="chip ok">그럴듯함 ${pct(t.ok, t.n)}</span> <span class="chip meh">애매함 ${pct(t.meh, t.n)}</span> <span class="chip bad">엉뚱함 ${pct(t.bad, t.n)}</span></p>
    <table><thead><tr><th>해외지</th><th>판정 수</th><th>그럴듯함</th><th>애매함</th><th>엉뚱함</th></tr></thead><tbody>${rows}</tbody></table>`;
}

render();
(async () => {
  const user = await claude.use("user");
  db = await claude.use("db");
  if (!db || !user) { $("#status").textContent = "저장 기능을 쓸 수 없습니다. 로그인한 상태로 claude.ai에서 열어 주세요."; return; }
  uid = await user.id();
  const can = user.can ? await user.can("data.write") : null;
  writable = !!uid && can !== false;
  if (!uid) { $("#status").textContent = "로그인 정보가 없어 판정을 저장할 수 없습니다."; render(); return; }
  if (await user.isOwner()) { $("#owner").hidden = false; $("#load").onclick = ownerSummary; }
  db.collection(`ratings/${uid}/items`).onSnapshot(snap => {
    const next = {}; snap.docs.forEach(d => { const x = d.data(); if (x && x.v) next[d.id] = x.v; });
    mine = next; render();
    $("#status").textContent = writable ? "판정은 바로 저장됩니다" : "보기 전용입니다";
    if (Object.keys(next).length) markRater().catch(() => {});  // 이전 버전에서 판정한 사람도 목록에 올린다
  }, () => { $("#status").textContent = "판정을 불러오지 못했습니다. 새로고침해 주세요."; });
  render();
})();
</script>
"""

if __name__ == "__main__":
    main(sys.argv[1])
