import type { RegionRow } from './api'

// 시도 줄임말 (앞 두 글자를 자르면 '전남광주통합특별시'가 '전남'이 된다)
const SIDO_SHORT: Record<string, string> = {
  서울특별시: '서울', 부산광역시: '부산', 대구광역시: '대구', 인천광역시: '인천', 광주광역시: '광주', 대전광역시: '대전', 울산광역시: '울산',
  세종특별자치시: '세종', 경기도: '경기', 강원특별자치도: '강원', 충청북도: '충북', 충청남도: '충남', 전북특별자치도: '전북', 전라남도: '전남',
  경상북도: '경북', 경상남도: '경남', 제주특별자치도: '제주', 전남광주통합특별시: '전남광주',
}
export const shortSido = (s: string) => SIDO_SHORT[s] ?? s

/** 기본 출발지 표시 이름. 5개 도시 이름('서울')은 그대로, 시군구 key('51_강릉시')는 '강원 강릉시'. */
export function originLabel(origin: string | null, rows: RegionRow[] | null): string | null {
  if (!origin) return null
  const r = rows?.find(x => x.key === origin)
  return r ? `${shortSido(r.sido)} ${r.name}` : origin.includes('_') ? origin.split('_')[1] : origin
}
