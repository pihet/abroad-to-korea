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
  query: { query_id: string; scene_tags: string[]; kept_tags: string[] | null; month: number; priority: Priority; origin: Origin | null }
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

  analyze: (input: { file?: Blob; demoPhotoId?: string; crop?: Crop | null }) => {
    const fd = new FormData()
    if (input.file) fd.append('image', input.file, 'upload.jpg')
    if (input.demoPhotoId) fd.append('demo_photo_id', input.demoPhotoId)
    if (input.crop) fd.append('crop', JSON.stringify(input.crop))
    return fetch('/api/analyze', { method: 'POST', body: fd }).then(r => json<AnalyzeResponse>(r))
  },

  recommend: (body: { query_id: string; travel_month: number; priority: Priority; origin?: Origin | null;
                      kept_tags?: string[]; limit?: number; offset?: number }) =>
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
