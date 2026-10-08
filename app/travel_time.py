"""코스 정류장 사이 이동 시간 (카카오). Map/ 폴더의 검증(2026-10-07)을 서버로 옮긴 것.

- 자동차: 카카오모빌리티 길찾기 (실시간 교통 반영이라 조회 시각마다 조금씩 다르다)
- 도보: 카카오맵 경로 조회. 하루 1,000건이라 직선 WALK_MAX_KM 이하 구간만 부른다
- 대중교통은 넣지 않는다 (도시 밖 관광지는 대부분 NO_RESULTS, 하루 1,000건)
- 결과는 서버 메모리에만 둔다 (카카오 약관상 결과를 쌓아 두는지 확인 전이라 파일로 저장하지 않음)

키: .env 의 KAKAO_REST_API_KEY, 없으면 KAKAO_CLIENT_ID (카카오 로그인 client_id 가 REST API 키와 같다)
"""

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .context import ROOT, haversine

WALK_MAX_KM = 2.0
CAR = "https://apis-navi.kakaomobility.com/v1/directions?origin={sx},{sy}&destination={ex},{ey}&priority=RECOMMEND&summary=true"
WALK = "https://dapi.kakao.com/v2/routing/walk?start_x={sx}&start_y={sy}&end_x={ex}&end_y={ey}"


def _key():
    for name in ("KAKAO_REST_API_KEY", "KAKAO_CLIENT_ID"):
        if os.environ.get(name):
            return os.environ[name].strip()
    env = ROOT / ".env"
    if env.exists():
        vals = dict(line.split("=", 1) for line in env.read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
        for name in ("KAKAO_REST_API_KEY", "KAKAO_CLIENT_ID"):
            if vals.get(name, "").strip():
                return vals[name].strip().strip('"').strip("'")
    return None


class TravelError(Exception):
    pass


class TravelTime:
    def __init__(self):
        self.key = _key()
        self.cache = {}
        self.calls = {"car": 0, "walk": 0}

    def _get(self, url):
        req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {self.key}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise TravelError(f"카카오 길찾기 오류 (HTTP {e.code})") from None
        except (urllib.error.URLError, TimeoutError):
            raise TravelError("카카오 길찾기에 연결하지 못했습니다") from None

    def _one(self, mode, a, b):
        """a, b = (위도, 경도). 경로가 없으면 None (실패가 아니라 결과)."""
        k = (mode, round(a[0], 5), round(a[1], 5), round(b[0], 5), round(b[1], 5))
        if k not in self.cache:
            p = {"sx": a[1], "sy": a[0], "ex": b[1], "ey": b[0]}
            self.calls[mode] += 1
            if mode == "car":
                route = (self._get(CAR.format(**p)).get("routes") or [{}])[0]
                s = route.get("summary") if route.get("result_code") == 0 else None
                self.cache[k] = {"min": round(s["duration"] / 60), "km": round(s["distance"] / 1000, 1)} if s else None
            else:
                d = self._get(WALK.format(**p))
                pr = (d.get("route") or {}).get("properties") if d.get("status") == "OK" else None
                self.cache[k] = {"min": round(pr["totalTime"] / 60), "km": round(pr["totalDistance"] / 1000, 1)} if pr else None
        return self.cache[k]

    def legs(self, points):
        """points = [(위도, 경도), ...] 순서대로. 구간마다 {car, walk, straight_km}."""
        if not self.key:
            raise TravelError("카카오 REST API 키가 없습니다 (.env 의 KAKAO_REST_API_KEY)")
        pairs = list(zip(points, points[1:]))

        def leg(ab):
            a, b = ab
            km = haversine(a, b)
            return {"straight_km": round(km, 1), "car": self._one("car", a, b),
                    "walk": self._one("walk", a, b) if km <= WALK_MAX_KM else None}
        with ThreadPoolExecutor(4) as ex:  # Map/ 검증과 같이 외부 동시 호출 최대 4건
            return list(ex.map(leg, pairs))
