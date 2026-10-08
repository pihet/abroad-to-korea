// API 계약 (docs/MVP_PLAN.md 5장, app/schemas.py 와 같은 모양). 화면은 이 타입만 알고 모델 코드는 모른다.

export type Priority = 'visual' | 'near'
export type Origin = '서울' | '부산' | '대구' | '광주' | '대전'

export interface DemoPhoto {
  photo_id: string
  place_name: string
  scene_label: string
  image_url: string
  artist: string
  license: string
  license_url: string
  source_page: string
  country_code: string
  country: string
  continent: string
}

export interface Tag { tag: string; score: number }

export interface AnalyzeResponse {
  is_example: boolean
  query_id: string
  scene_tags: Tag[]
  image: { width: number; height: number; cropped: boolean }
  excluded_sigungu: { key: string; name: string } | null
  media_asset_id: string | null
}

export interface AuthUser {
  id: string; email: string; nickname: string; status: string; email_verified: boolean
}

export const authApi = {
  me: () => fetch('/api/auth/me').then(r => json<AuthUser>(r)),
  signup: (body: { email: string; nickname: string; password: string }) =>
    fetch('/api/auth/signup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(r => json<{ ok: boolean; message: string; verification_token?: string }>(r)),
  verifyEmail: (token: string) =>
    fetch('/api/auth/verify-email', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) })
      .then(r => json<{ ok: boolean }>(r)),
  login: (body: { email: string; password: string }) =>
    fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => json<AuthUser>(r)),
  logout: () => fetch('/api/auth/logout', { method: 'POST' }).then(r => json<{ ok: boolean }>(r)),
  oauthStart: (provider: 'google' | 'kakao') =>
    fetch(`/api/auth/oauth/${provider}/start`).then(r => json<{ authorization_url: string }>(r)),
  savedRegions: () => fetch('/api/me/saved-regions').then(r => json<{ regions: string[] }>(r)),
  saveRegion: (region_key: string) =>
    fetch('/api/me/saved-regions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ region_key }) }).then(r => json(r)),
  unsaveRegion: (regionKey: string) =>
    fetch(`/api/me/saved-regions/${encodeURIComponent(regionKey)}`, { method: 'DELETE' }).then(r => json(r)),
}

export interface MonthPoint { month: string; visitors: number; index: number }

export interface Candidate {
  rank: number
  visual_rank: number
  sigungu: { key: string; name: string; sido: string }
  attraction: {
    id: string; name: string; address: string | null; latitude: number | null; longitude: number | null
    image_url: string; license: string; source: string
  }
  visual: { similarity: number; vote: number }
  similar_tags: string[]
  different_tags: string[]
  congestion: {
    month: number | null; index: number | null; visitors: number; basis: 'forecast' | 'actual' | 'annual'; basis_month: string; monthly: MonthPoint[]
  } | null
  climate: { month: number; temp_c: number; rain_days: number; comfort: number } | null
  distance_km: number | null
  map_links: { kakao: string | null; naver: string | null }
  rerank: { visual_component: number; condition_component: number | null; condition_value: number | null }
}

export interface RecommendResponse {
  is_example: boolean
  query: { query_id: string; scene_tags: string[]; kept_tags: string[] | null; month: number | null; priority: Priority; origin: Origin | null
           filters: FilterKey[]; sido: string | null; allowed_regions: number | null
           excluded_sigungu: { key: string; name: string } | null }
  model: { visual: string; rerank: string; priorities: Priority[] }
  total_candidates: number
  candidates: Candidate[]
  data_sources: { name: string; as_of: string; period: string }[]
}

export interface Crop { x: number; y: number; w: number; h: number }

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `요청이 실패했습니다 (${res.status}).`
    try { const b = await res.json(); if (typeof b.detail === 'string') msg = b.detail } catch { /* 본문 없음 */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export const api = {
  demoPhotos: () => fetch('/api/demo-photos').then(r => json<{ photos: DemoPhoto[] }>(r)).then(r => r.photos),

  analyze: (input: { file?: Blob; demoPhotoId?: string; crop?: Crop | null; sourceAttractionId?: string; retainPhoto?: boolean; storePhoto?: boolean }) => {
    const fd = new FormData()
    if (input.file) fd.append('image', input.file, 'upload.jpg')
    if (input.demoPhotoId) fd.append('demo_photo_id', input.demoPhotoId)
    if (input.crop) fd.append('crop', JSON.stringify(input.crop))
    if (input.sourceAttractionId) fd.append('source_attraction_id', input.sourceAttractionId)
    if (input.retainPhoto) fd.append('retain_photo', 'true')
    if (input.storePhoto === false) fd.append('store_photo', 'false')
    return fetch('/api/analyze', { method: 'POST', body: fd }).then(r => json<AnalyzeResponse>(r))
  },

  convert: async (file: Blob) => {
    const fd = new FormData()
    fd.append('image', file, 'upload.heic')
    const r = await fetch('/api/convert', { method: 'POST', body: fd })
    if (!r.ok) await json(r)  // 오류 문구를 그대로 던진다
    return r.blob()
  },

  recommend: (body: { query_id: string; priority: Priority; origin?: Origin | null;
                      kept_tags?: string[]; limit?: number; offset?: number; filters?: FilterKey[]; sido?: string | null }) =>
    fetch('/api/recommend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(r => json<RecommendResponse>(r)),

  feedback: (body: { query_id: string; sigungu_key: string; attraction_id: string; value: 1 | -1 }) =>
    fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(r => json<{ ok: boolean }>(r)),
}

// 여행 월 선택을 없애면서 'season'(고른 달에 가기 좋은 곳)은 화면에서 뺐다. API는 월과 함께 보낼 때만 받는다
// 'crowd'(덜 붐비는 곳)도 뺐다: 혼잡도는 검색 조건이 아니라 지역 상세에서만 보여 준다. API는 아직 받는다
export const PRIORITY_LABEL: Record<Priority, string> = {
  visual: '사진과 최대한 비슷하게',
  near: '출발지에서 가까운 곳',
}
export const ORIGINS: Origin[] = ['서울', '부산', '대구', '광주', '대전']

export interface ActivityGroup { key: string; label: string; count: number }
export interface ActivityItem {
  id: string; name: string; group: string; kind: string; lat: number; lon: number
  address: string | null; image_url: string | null; license: string | null; distance_km: number | null
  period?: string | null; schedule?: string | null; menu?: string | null
}
export interface ActivitiesResponse {
  is_example: boolean; sigungu_key: string; month: number | null
  anchor: { id: string; name: string; lat: number; lon: number } | null
  groups: ActivityGroup[]; items: ActivityItem[]; notes: string[]
}

export const activitiesApi = (sigunguKey: string, attractionId?: string) => {
  const q = new URLSearchParams({ sigungu_key: sigunguKey })
  if (attractionId) q.set('attraction_id', attractionId)
  return fetch(`/api/activities?${q}`).then(r => json<ActivitiesResponse>(r))
}

export type FilterKey = 'sea' | 'mountain' | 'calm' | 'city' | 'rural' | 'mild'
export interface RegionRow {
  key: string; name: string; sido: string; coast_km: number | null; mountain_n: number; urban_share: number | null
  visitors: number | null; congestion_index: number | null; temp_c: number | null; rain_days: number | null
  flags: Record<FilterKey, boolean>; distance_km: number | null
  photo: { attraction_id: string; name: string; image_url: string; license: string; tags?: string[] } | null
  // 분류 칩용 사진: 그 시군구의 바다·산숲·도시 관광지 사진 중 대표 (없으면 null)
  kind_photos?: Partial<Record<'sea' | 'mountain' | 'city', RegionRow['photo']>>
}
export interface RegionsResponse {
  is_example: boolean; month: number
  filters: { key: FilterKey; label: string; basis: string }[]
  sidos: string[]; regions: RegionRow[]
}
export const regionsApi = (origin?: Origin | null) =>
  fetch(`/api/regions${origin ? `?origin=${encodeURIComponent(origin)}` : ''}`).then(r => json<RegionsResponse>(r))


export interface MonthRow {
  month: number; temp_c: number | null; rain_days: number | null
  visitors: number | null; congestion_index: number | null; basis: 'forecast' | 'actual' | null; basis_month: string | null
}
export interface Neighborhood {
  code: string; name: string; total: number; groups: Record<string, number>; rank: number | null
  label: [number, number]; geometry: GeoJSON.Geometry; n_food: number
}
export interface RegionProfile {
  is_example: boolean; month: number
  region: RegionRow & { flags: Record<FilterKey, boolean> }
  photo: RegionRow['photo']
  filters: { key: FilterKey; label: string; basis: string }[]
  months: MonthRow[]; neighborhoods: Neighborhood[]; focus: [number, number, number, number] | null; notes: string[]
  food: { n_places: number; n_menus: number; top: { name: string; places: number }[] }
}
export const profileApi = (key: string) =>
  fetch(`/api/regions/${encodeURIComponent(key)}/profile`).then(r => json<RegionProfile>(r))

export interface RankingItem { key: string; name: string; sido: string; value: number; unit: string; photo: RegionRow['photo'] }
export interface RankingList { id: string; title: string; basis: string; items: RankingItem[]; empty?: string }
export const rankingsApi = () =>
  fetch(`/api/rankings`).then(r => json<{ lists: RankingList[] }>(r)).then(r => r.lists)


export interface DongFood {
  code: string; total: number; with_menu: number; note: string
  items: { id: string; name: string; kind: string; address: string | null; image_url: string | null; license: string | null; menu: string | null }[]
}
export const dongFoodApi = (key: string, code: string) =>
  fetch(`/api/regions/${encodeURIComponent(key)}/dongs/${code}/food`).then(r => json<DongFood>(r))

export interface DongActivities {
  code: string; groups: ActivityGroup[]
  items: { id: string; name: string; group: string; kind: string; lat: number; lon: number; image_url: string | null
           license: string | null; address: string | null; menu: string | null }[]
}
export const dongActivitiesApi = (key: string, code: string) =>
  fetch(`/api/regions/${encodeURIComponent(key)}/dongs/${code}/activities`).then(r => json<DongActivities>(r))

export type RainResult = { start: string; end: string; rule: string } & (
  | { basis: 'forecast'; rainy_days: number; days: { date: string; rain_mm: number | null; prob: number | null }[] }
  | { basis: 'history'; years: string | null; n_years: number; years_with_rain: number; avg_rainy_days: number | null
      days: { date: string; rainy_years: number; years: number; by_year: Record<string, number> }[] })
export const rainApi = (key: string, start: string, end: string) =>
  fetch(`/api/regions/${encodeURIComponent(key)}/rain?start=${start}&end=${end}`).then(r => json<RainResult>(r))

export interface Festival {
  id: string; name: string; region_key: string; address: string | null; image_url: string | null; license: string | null
  start: string; end: string; starts_in_range: boolean; region: { key: string; name: string; sido: string }
}
export const festivalsApi = (days = 7) =>
  fetch(`/api/festivals?days=${days}`).then(r => json<{ start: string; end: string; total: number; items: Festival[]; basis: string }>(r))

export interface CourseStop {
  order: number; id: string | null; name: string; overview: string; lat: number | null; lon: number | null
  group: string | null; kind: string | null; image_url: string | null; license: string | null; region: string | null
}
export interface Course { id: string; title: string; stops: CourseStop[]; distance: string | null; taketime: string | null; theme: string | null; regions: Record<string, number> }
export interface CoursesResponse { is_example: boolean; total: number; items: Course[]; coverage: { loaded: number; listed: number }; notes: string[] }
export const coursesApi = (key: string) => fetch(`/api/regions/${encodeURIComponent(key)}/courses`).then(r => json<CoursesResponse>(r))

export interface SearchHit { name: string; region_key: string; region_name: string | null; sido: string | null }
export interface SearchResult {
  q: string
  dongs: (SearchHit & { code: string; n_acts: number })[]
  places: (SearchHit & { id: string; kind: string; group: string | null; dong_code: string | null; dong_name: string | null })[]
}
export const searchApi = (q: string, signal?: AbortSignal) =>
  fetch(`/api/search?q=${encodeURIComponent(q)}&limit=12`, { signal }).then(r => json<SearchResult>(r))

export interface PlaceDetail { id: string; title: string | null; overview: string | null; tel: string | null; homepage: string | null; source: string }
export const placeDetailApi = (cid: string) => fetch(`/api/places/${cid}/detail`).then(r => json<PlaceDetail>(r))

export interface PlacePhotos { id: string; photos: { url: string; name: string | null; license: string }[]; source: string }
export const placePhotosApi = (cid: string) => fetch(`/api/places/${cid}/photos`).then(r => json<PlacePhotos>(r))
