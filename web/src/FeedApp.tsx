import { useEffect, useMemo, useRef, useState } from 'react'
import { authApi, festivalsApi, regionsApi, type AuthUser, type Festival, type RegionRow } from './api'
import { FeedRegion } from './FeedRegion'
import { FeedSearch, type Source } from './FeedSearch'
import { RegionSearch } from './RegionSearch'
import { FeedExplore } from './FeedExplore'
import { useDragScroll } from './dragScroll'
import { AccountModal } from './AccountModal'
import './feed.css'

// 메인 화면 (인스타그램형): 홈 피드 · 탐색 · 사진으로 찾기 · 저장 + 지역 검색 · 지역 상세.
// 사진은 공공누리 3유형이 섞여 있어 정사각형으로 자르지 않는다 (object-fit: contain).

type Tab = 'home' | 'explore' | 'search' | 'saved'
// coverTags: 동그라미 사진은 그 분류에 맞는 해시태그가 붙은 관광지 사진으로 고른다 (앞에 있는 태그부터)
type Story = { id: string; label: string; match: (r: RegionRow) => boolean; coverTags?: string[] }
const STORIES: Story[] = [
  { id: 'all', label: '전체', match: () => true },
  { id: 'sea', label: '바다', match: r => r.flags.sea, coverTags: ['#해변', '#해안절경', '#바다'] },
  { id: 'mountain', label: '산·숲', match: r => r.flags.mountain, coverTags: ['#산', '#자연휴양림', '#산숲'] },
  { id: 'rural', label: '시골', match: r => r.flags.rural, coverTags: ['#체험마을', '#마을관광지', '#고택'] },
  { id: 'city', label: '도시', match: r => r.flags.city, coverTags: ['#분수', '#골목길'] },
]
const PAGE = 8

// 하루 동안은 같은 순서 (새로 고칠 때마다 피드가 뒤섞이지 않게)
function dailyShuffle<T>(xs: T[]): T[] {
  let seed = Number(new Date().toISOString().slice(0, 10).replace(/-/g, ''))
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280
  const a = [...xs]
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]] }
  return a
}

const md = (iso: string) => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`

// 시도 줄임말 (앞 두 글자를 자르면 '전남광주통합특별시'가 '전남'이 된다)
const SIDO_SHORT: Record<string, string> = {
  서울특별시: '서울', 부산광역시: '부산', 대구광역시: '대구', 인천광역시: '인천', 광주광역시: '광주', 대전광역시: '대전', 울산광역시: '울산',
  세종특별자치시: '세종', 경기도: '경기', 강원특별자치도: '강원', 충청북도: '충북', 충청남도: '충남', 전북특별자치도: '전북', 전라남도: '전남',
  경상북도: '경북', 경상남도: '경남', 제주특별자치도: '제주', 전남광주통합특별시: '전남광주',
}
const shortSido = (s: string) => SIDO_SHORT[s] ?? s

const loadSaved = (): string[] => { try { return JSON.parse(localStorage.getItem('feed-saved') || '[]') } catch { return [] } }

// 해시태그는 사진 속 관광지의 분류로 (해변 → #바다 #해변). 시군구 전체 특징(바다·산숲 둘 다)은 지역 상세에서만
function caption(r: RegionRow) {
  return [...(r.photo?.tags ?? []), r.flags.city ? '#도시' : '#시골소도시'].join(' ')
}

const Icon = {
  home: <path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  plus: <><rect x="3" y="3" width="18" height="18" rx="5" /><path d="M12 8v8M8 12h8" /></>,
  bookmark: <path d="M6 3h12v18l-6-5-6 5z" />,
  heart: <path d="M12 20s-7-4.4-9.2-8.6C1.2 8.2 3 4.5 6.6 4.5c2.2 0 3.6 1.3 5.4 3.3 1.8-2 3.2-3.3 5.4-3.3 3.6 0 5.4 3.7 3.8 6.9C19 15.6 12 20 12 20z" />,
  photo: <><rect x="3" y="5" width="18" height="15" rx="3" /><circle cx="12" cy="12.5" r="3.5" /><path d="M8 5l1.5-2h5L16 5" /></>,
  map: <><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z" /><path d="M9 4v14M15 6v14" /></>,
}
const Svg = ({ d, fill }: { d: React.ReactNode; fill?: boolean }) =>
  <svg viewBox="0 0 24 24" className={fill ? 'ic fill' : 'ic'} aria-hidden="true">{d}</svg>

export default function FeedApp() {
  useDragScroll()
  const [rows, setRows] = useState<RegionRow[] | null>(null)
  const [fest, setFest] = useState<{ start: string; end: string; total: number; items: Festival[] } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('home')
  const [story, setStory] = useState('all')
  const [shown, setShown] = useState(PAGE)
  // 지역 상세는 주소로도 연다: #region=50_제주시 (공유·바로가기용)
  const [open, setOpenState] = useState<string | null>(() => new URLSearchParams(window.location.hash.slice(1)).get('region'))
  const setOpen = (k: string | null) => { setOpenState(k); history.replaceState(null, '', k ? `#region=${encodeURIComponent(k)}` : window.location.pathname) }
  const [start, setStart] = useState<Source | null>(null)
  const [finding, setFinding] = useState(false)  // 지역 검색 화면
  const [openDong, setOpenDong] = useState<string | null>(null)  // 검색에서 동네·장소로 들어오면 그 동네를 고른 채로
  const [saved, setSaved] = useState<string[]>(loadSaved)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [accountOpen, setAccountOpen] = useState(false)
  const more = useRef<HTMLDivElement>(null)

  useEffect(() => {
    regionsApi().then(r => setRows(dailyShuffle(r.regions.filter(x => x.photo)))).catch(e => setErr(e.message))
    festivalsApi().then(setFest).catch(() => setFest(null))
  }, [])
  useEffect(() => {
    authApi.me().then(setUser).catch(() => {})
  }, [])
  useEffect(() => {
    if (!user) return
    authApi.savedRegions().then(async ({ regions: remote }) => {
      const merged = [...new Set([...loadSaved(), ...remote])]
      setSaved(merged)
      await Promise.all(merged.filter(k => !remote.includes(k)).map(k => authApi.saveRegion(k)))
    }).catch(() => {})
  }, [user])
  useEffect(() => { try { localStorage.setItem('feed-saved', JSON.stringify(saved)) } catch { /* 저장소 없음 */ } }, [saved])
  useEffect(() => { setShown(PAGE); window.scrollTo(0, 0) }, [story, tab])
  useEffect(() => {
    const onHash = () => setOpenState(new URLSearchParams(window.location.hash.slice(1)).get('region'))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const feed = useMemo(() => (rows ?? []).filter(STORIES.find(s => s.id === story)!.match), [rows, story])
  // 피드 끝에 닿으면 다음 묶음 (무한 스크롤)
  useEffect(() => {
    const el = more.current
    if (!el) return
    const io = new IntersectionObserver(es => es[0].isIntersecting && setShown(n => n + PAGE), { rootMargin: '600px' })
    io.observe(el)
    return () => io.disconnect()
  }, [tab, feed.length])

  const toggle = (k: string) => {
    const removing = saved.includes(k)
    setSaved(removing ? saved.filter(x => x !== k) : [...saved, k])
    if (user) (removing ? authApi.unsaveRegion(k) : authApi.saveRegion(k)).catch(() => {})
  }
  const changeUser = (next: AuthUser | null) => {
    if (next === null) setSaved([])
    setUser(next)
  }
  // 분류마다 서로 다른 1유형 사진을 고른다
  const covers = useMemo(() => {
    const used = new Set<string>(), out: Record<string, string | undefined> = {}
    for (const s of STORIES) {
      const ok = (r: RegionRow) => s.match(r) && !!r.photo && !used.has(r.photo.image_url)
      const tagged = (s.coverTags ?? []).map(t => (rows ?? []).find(r => ok(r) && (r.photo?.tags ?? []).includes(t))).find(Boolean)
      const r = tagged ?? (rows ?? []).find(ok)
      if (r) { used.add(r.photo!.image_url); out[s.id] = r.photo!.image_url }
    }
    return out
  }, [rows])
  const cover = (s: Story) => covers[s.id]
  const goSearch = () => setTab('search')
  // 지역 상세의 "이 사진과 닮은 다른 곳 찾기": 출발 관광지를 넘겨 같은 시군구가 다시 1위로 나오지 않게 한다
  const searchPhoto = async (p: { attraction_id: string; image_url: string }) => {
    const blob = await fetch(p.image_url).then(r => r.blob())
    setOpen(null); setTab('search')
    setStart({ kind: 'file', file: blob, url: URL.createObjectURL(blob), sourceAttractionId: p.attraction_id, persist: false })
  }

  return (
    <div className="ig">
      <header className="ig-top">
        <b className="ig-logo">닮은꼴<i>.</i></b>
        <div className="ig-top-act">
          <button type="button" className="account-trigger" onClick={() => setAccountOpen(true)}>{user ? user.nickname : '로그인'}</button>
          <button type="button" onClick={() => setFinding(true)} aria-label="지역 검색"><Svg d={Icon.search} /></button>
          <button type="button" onClick={goSearch} aria-label="사진으로 찾기"><Svg d={Icon.photo} /></button>
        </div>
      </header>

      {err && <p className="ig-err">{err}</p>}
      {!rows && !err && <p className="ig-wait">불러오는 중…</p>}

      {rows && tab === 'home' && <>
        <nav className="ig-stories" aria-label="분류" data-drag>
          {STORIES.map(s => (
            <button key={s.id} type="button" aria-pressed={story === s.id} onClick={() => setStory(s.id)}>
              <span className="ring"><span className="in">{cover(s) && <img src={cover(s)} alt="" />}</span></span>
              <small>{s.label}</small>
            </button>
          ))}
        </nav>

        <button type="button" className="ig-cta" onClick={goSearch}>
          <Svg d={Icon.photo} /><span><b>가고 싶은 해외 사진이 있나요?</b><small>사진을 올리면 분위기가 닮은 국내 여행지를 찾아 드려요</small></span>
        </button>

        {story === 'all' && fest && fest.items.length > 0 && (
          <section className="ig-strip fest">
            <div className="ig-strip-head"><b>이번 주 축제</b><small>{md(fest.start)} ~ {md(fest.end)} · {fest.total}개 · 누르면 그 지역을 보여 드려요</small></div>
            <ol data-drag>
              {fest.items.map(x => (
                <li key={x.id}><button type="button" onClick={() => setOpen(x.region_key)}>
                  <span className="ph">{x.image_url ? <img src={x.image_url} alt={x.name} loading="lazy" /> : <i>{x.name}</i>}</span>
                  <span className={x.starts_in_range ? 'when new' : 'when'}>{x.starts_in_range ? `${md(x.start)} 시작` : `${md(x.end)}까지`}</span>
                  <b>{x.name}</b><small>{shortSido(x.region.sido)} {x.region.name}</small>
                </button></li>
              ))}
            </ol>
          </section>
        )}

        <ul className="ig-feed">
          {feed.slice(0, shown).map(r => (
            <li key={r.key} className="post">
              <div className="post-head">
                <span className="av">{r.photo ? <img src={r.photo.image_url} alt="" /> : <i>{r.name.slice(0, 1)}</i>}</span>
                <span><b>{r.name}</b><small>{r.sido}</small></span>
              </div>
              <button type="button" className="post-ph" onClick={() => setOpen(r.key)} aria-label={`${r.name} 자세히 보기`}>
                <img src={r.photo!.image_url} alt={r.photo!.name} loading="lazy" />
              </button>
              <div className="post-act">
                <button type="button" aria-pressed={saved.includes(r.key)} onClick={() => toggle(r.key)} aria-label="저장"><Svg d={Icon.heart} fill={saved.includes(r.key)} /></button>
                <button type="button" onClick={() => setOpen(r.key)} aria-label="지도와 동네 보기"><Svg d={Icon.map} /></button>
                <button type="button" className="post-more" onClick={() => setOpen(r.key)}>자세히 보기</button>
              </div>
              <p className="post-cap"><b>{r.photo!.name}</b> {caption(r)}</p>
            </li>
          ))}
        </ul>
        {shown < feed.length ? <div ref={more} className="ig-wait">더 불러오는 중…</div> : <p className="ig-foot">사진·정보 한국관광공사 TourAPI (공공누리 제1·3유형) · 자세한 출처는 각 지역 상세 맨 아래</p>}
      </>}

      {tab === 'explore' && <FeedExplore onPick={p => { setStart({ kind: 'demo', photo: p, url: p.image_url }); setTab('search') }} />}

      {rows && tab === 'saved' && (
        saved.length === 0 ? <p className="ig-wait">하트를 누른 곳이 여기에 모여요.</p> : (
          <div className="ig-grid">
            {rows.filter(r => saved.includes(r.key)).map(r => (
              <button key={r.key} type="button" onClick={() => setOpen(r.key)} aria-label={`${r.sido} ${r.name}`}>
                <img src={r.photo!.image_url} alt={r.photo!.name} loading="lazy" />
              </button>
            ))}
          </div>
        )
      )}

      <div hidden={tab !== 'search'}>
        <FeedSearch start={start} saved={saved} onToggleSave={toggle} onOpen={setOpen} loggedIn={user !== null} />
      </div>

      <nav className="ig-tabs" aria-label="메뉴">
        <button type="button" aria-pressed={tab === 'home'} onClick={() => setTab('home')}><Svg d={Icon.home} fill={tab === 'home'} /><small>홈</small></button>
        <button type="button" aria-pressed={tab === 'explore'} onClick={() => setTab('explore')}><Svg d={Icon.search} /><small>탐색</small></button>
        <button type="button" aria-pressed={tab === 'search'} onClick={goSearch}><Svg d={Icon.plus} /><small>사진으로 찾기</small></button>
        <button type="button" aria-pressed={tab === 'saved'} onClick={() => setTab('saved')}><Svg d={Icon.bookmark} fill={tab === 'saved'} /><small>저장</small></button>
      </nav>

      {finding && rows && <RegionSearch rows={rows} shortSido={shortSido} onClose={() => setFinding(false)}
        onPick={(k, dong) => { setFinding(false); setOpenDong(dong ?? null); setOpen(k) }} />}
      {open && <FeedRegion regionKey={open} initialDong={openDong} saved={saved.includes(open)} onToggleSave={() => toggle(open)} onClose={() => { setOpen(null); setOpenDong(null) }}
        onSearchPhoto={p => { searchPhoto(p).catch(() => {}) }} />}
      {accountOpen && <AccountModal user={user} onUser={changeUser} onClose={() => setAccountOpen(false)} />}
    </div>
  )
}
