// API 계약 (docs/MVP_PLAN.md 5장, app/schemas.py 와 같은 모양). 화면은 이 타입만 알고 모델 코드는 모른다.

export type Priority = 'visual' | 'crowd' | 'near' | 'season'
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
}

export interface Tag { tag: string; score: number }

export interface AnalyzeResponse {
  is_example: boolean
  query_id: string
  scene_tags: Tag[]
  image: { width: number; height: number; cropped: boolean }
  excluded_sigungu: { key: string; name: string } | null
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
    month: number; index: number; visitors: number; basis: 'forecast' | 'actual'; basis_month: string; monthly: MonthPoint[]
  } | null
  climate: { month: number; temp_c: number; rain_days: number; comfort: number } | null
  distance_km: number | null
  map_links: { kakao: string | null; naver: string | null }
  rerank: { visual_component: number; condition_component: number | null; condition_value: number | null }
}

export interface RecommendResponse {
  is_example: boolean
  query: { query_id: string; scene_tags: string[]; kept_tags: string[] | null; month: number; priority: Priority; origin: Origin | null
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

  analyze: (input: { file?: Blob; demoPhotoId?: string; crop?: Crop | null; sourceAttractionId?: string }) => {
    const fd = new FormData()
    if (input.file) fd.append('image', input.file, 'upload.jpg')
    if (input.demoPhotoId) fd.append('demo_photo_id', input.demoPhotoId)
    if (input.crop) fd.append('crop', JSON.stringify(input.crop))
    if (input.sourceAttractionId) fd.append('source_attraction_id', input.sourceAttractionId)
    return fetch('/api/analyze', { method: 'POST', body: fd }).then(r => json<AnalyzeResponse>(r))
  },

  convert: async (file: Blob) => {
    const fd = new FormData()
    fd.append('image', file, 'upload.heic')
    const r = await fetch('/api/convert', { method: 'POST', body: fd })
    if (!r.ok) await json(r)  // 오류 문구를 그대로 던진다
    return r.blob()
  },

  recommend: (body: { query_id: string; travel_month: number; priority: Priority; origin?: Origin | null;
                      kept_tags?: string[]; limit?: number; offset?: number; filters?: FilterKey[]; sido?: string | null }) =>
    fetch('/api/recommend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(r => json<RecommendResponse>(r)),

  feedback: (body: { query_id: string; sigungu_key: string; attraction_id: string; value: 1 | -1 }) =>
    fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(r => json<{ ok: boolean }>(r)),
}

export const PRIORITY_LABEL: Record<Priority, string> = {
  visual: '사진과 최대한 비슷하게',
  crowd: '덜 붐비는 곳',
  near: '출발지에서 가까운 곳',
  season: '고른 달에 가기 좋은 곳',
}
export const ORIGINS: Origin[] = ['서울', '부산', '대구', '광주', '대전']

export interface ActivityGroup { key: string; label: string; count: number }
export interface ActivityItem {
  id: string; name: string; group: string; kind: string; lat: number; lon: number
  address: string | null; image_url: string | null; license: string | null; distance_km: number | null
  period?: string | null; schedule?: string | null
}
export interface ActivitiesResponse {
  is_example: boolean; sigungu_key: string; month: number
  anchor: { id: string; name: string; lat: number; lon: number } | null
  groups: ActivityGroup[]; items: ActivityItem[]; notes: string[]
}

export const activitiesApi = (sigunguKey: string, month: number, attractionId?: string) => {
  const q = new URLSearchParams({ sigungu_key: sigunguKey, month: String(month) })
  if (attractionId) q.set('attraction_id', attractionId)
  return fetch(`/api/activities?${q}`).then(r => json<ActivitiesResponse>(r))
}

export type FilterKey = 'sea' | 'mountain' | 'calm' | 'city' | 'rural' | 'mild'
export interface RegionRow {
  key: string; name: string; sido: string; coast_km: number | null; mountain_n: number; urban_share: number | null
  visitors: number | null; congestion_index: number | null; temp_c: number | null; rain_days: number | null
  flags: Record<FilterKey, boolean>; distance_km: number | null
  photo: { attraction_id: string; name: string; image_url: string; license: string } | null
}
export interface RegionsResponse {
  is_example: boolean; month: number
  filters: { key: FilterKey; label: string; basis: string }[]
  sidos: string[]; regions: RegionRow[]
}
export const regionsApi = (month: number, origin?: Origin | null) =>
  fetch(`/api/regions?month=${month}${origin ? `&origin=${encodeURIComponent(origin)}` : ''}`).then(r => json<RegionsResponse>(r))

export interface Filters { month: number; sido: string | null; keys: FilterKey[] }
export const matches = (r: RegionRow, f: Filters) => f.keys.every(k => r.flags[k]) && (!f.sido || r.sido === f.sido)

export interface MonthRow {
  month: number; temp_c: number | null; rain_days: number | null
  visitors: number | null; congestion_index: number | null; basis: 'forecast' | 'actual' | null; basis_month: string | null
}
export interface Neighborhood {
  code: string; name: string; total: number; groups: Record<string, number>; rank: number | null
  label: [number, number]; geometry: GeoJSON.Geometry
}
export interface RegionProfile {
  is_example: boolean; month: number
  region: RegionRow & { flags: Record<FilterKey, boolean> }
  photo: RegionRow['photo']
  filters: { key: FilterKey; label: string; basis: string }[]
  months: MonthRow[]; neighborhoods: Neighborhood[]; focus: [number, number, number, number] | null; notes: string[]
}
export const profileApi = (key: string, month: number) =>
  fetch(`/api/regions/${encodeURIComponent(key)}/profile?month=${month}`).then(r => json<RegionProfile>(r))

export interface RankingItem { key: string; name: string; sido: string; value: number; unit: string; photo: RegionRow['photo'] }
export interface RankingList { id: string; title: string; basis: string; items: RankingItem[]; empty?: string }
export const rankingsApi = (month: number) =>
  fetch(`/api/rankings?month=${month}`).then(r => json<{ lists: RankingList[] }>(r)).then(r => r.lists)
