from flask import Flask, request, jsonify
import os
import time
import json
import requests
import math
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client
from urllib.parse import quote
import logging
from typing import List, Dict, Optional
import threading
from bs4 import BeautifulSoup
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Selenium import를 try-except로 감싸서 Railway 환경에서 fallback 처리
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
    logger.info("Selenium 모듈 로드 성공")
except ImportError as e:
    SELENIUM_AVAILABLE = False
    logger.warning(f"Selenium 모듈 로드 실패: {e}")
    logger.info("Requests 기반 크롤링으로 fallback 합니다.")

# Flask 앱 초기화
app = Flask(__name__)

# 환경 변수 로드
load_dotenv()

# API 키 로드
KAKAO_API_KEY = os.getenv("NEXT_PUBLIC_KAKAO_REST_API_KEY")

# Supabase 클라이언트 안전하게 초기화
supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
supabase_key = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

supabase = None
if not supabase_url or not supabase_key:
    logger.error("Supabase 환경 변수가 설정되지 않았습니다.")
    logger.error(f"SUPABASE_URL: {'설정됨' if supabase_url else '미설정'}")
    logger.error(f"SUPABASE_KEY: {'설정됨' if supabase_key else '미설정'}")
else:
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        logger.info("Supabase 클라이언트 초기화 성공")
    except Exception as e:
        logger.error(f"Supabase 클라이언트 초기화 실패: {e}")
        supabase = None

# KAKAO API 키 확인
if not KAKAO_API_KEY:
    logger.error("KAKAO API 키가 설정되지 않았습니다.")
else:
    logger.info("KAKAO API 키 설정 확인됨")

class RequestsCrawler:
    """Requests 기반 크롤러 (Railway 환경 대안)"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.processed_cafes = set()

    def search_nearby_cafes(self, lat: float, lng: float, limit: int = 5) -> List[Dict]:
        """Kakao API를 사용해서 근처 카페 검색"""
        cafe_data = []

        if not KAKAO_API_KEY:
            logger.error("Kakao API 키가 필요합니다.")
            return cafe_data

        try:
            # Kakao Local API로 카페 검색
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
            params = {
                "query": "카페",
                "x": lng,
                "y": lat,
                "radius": 1000,  # 1km 반경
                "size": limit,
                "sort": "distance"
            }

            response = self.session.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('documents'):
                for idx, place in enumerate(data['documents'][:limit]):
                    try:
                        cafe_info = {
                            "name": place.get('place_name', ''),
                            "category": place.get('category_name', '카페'),
                            "address": place.get('address_name', ''),
                            "locationKeyword": f"{lat:.5f},{lng:.5f}",
                            "latitude": float(place.get('y', 0)),
                            "longitude": float(place.get('x', 0)),
                            "business_district": self.get_business_district_by_coords(lat, lng),
                            "menu_items": self.generate_sample_menu(),  # 샘플 메뉴 생성
                            "phone": place.get('phone', ''),
                            "place_url": place.get('place_url', '')
                        }

                        cafe_key = f"{cafe_info['name']}_{cafe_info['address']}"
                        if cafe_key not in self.processed_cafes:
                            cafe_data.append(cafe_info)
                            self.processed_cafes.add(cafe_key)
                            logger.info(f"카페 수집: {cafe_info['name']} ({cafe_info['address']})")

                    except Exception as e:
                        logger.warning(f"카페 데이터 처리 오류: {e}")
                        continue

            logger.info(f"Kakao API로 {len(cafe_data)}개 카페 수집 완료")
            return cafe_data

        except Exception as e:
            logger.error(f"Kakao API 크롤링 오류: {e}")
            return cafe_data

    def generate_sample_menu(self) -> List[Dict]:
        """샘플 메뉴 생성 (실제 메뉴는 별도 API나 크롤링 필요)"""
        sample_menus = [
            {"name": "아메리카노", "price": 4500, "description": "진한 원두의 깔끔한 맛", "image_url": ""},
            {"name": "카페라떼", "price": 5000, "description": "부드러운 우유와 에스프레소", "image_url": ""},
            {"name": "카푸치노", "price": 5500, "description": "폭신한 우유거품", "image_url": ""},
            {"name": "바닐라라떼", "price": 5800, "description": "달콤한 바닐라 향", "image_url": ""},
            {"name": "아이스티", "price": 4000, "description": "시원한 홍차", "image_url": ""}
        ]
        # 랜덤하게 3-5개 메뉴 선택
        import random
        return random.sample(sample_menus, random.randint(3, 5))

    def get_business_district_by_coords(self, lat: float, lng: float) -> str:
        """좌표 기반 업무지구 판단"""
        # 강남구 (강남 업무지구)
        if 37.48 <= lat <= 37.53 and 127.01 <= lng <= 127.11:
            return "강남 업무지구"
        # 영등포구 (여의도 업무지구)
        elif 37.51 <= lat <= 37.53 and 126.90 <= lng <= 126.95:
            return "여의도 업무지구"
        # 중구 (종로/광화문 업무지구)
        elif 37.56 <= lat <= 37.58 and 126.97 <= lng <= 127.00:
            return "종로/광화문 업무지구"
        # 강남구 삼성동 (삼성동 업무지구)
        elif 37.50 <= lat <= 37.52 and 127.05 <= lng <= 127.08:
            return "삼성동 업무지구"
        # 마포구 (상암 업무지구)
        elif 37.57 <= lat <= 37.59 and 126.88 <= lng <= 126.91:
            return "상암 업무지구"
        # 분당 (판교 업무지구)
        elif 37.38 <= lat <= 37.42 and 127.10 <= lng <= 127.13:
            return "판교 업무지구"
        else:
            return "기타"

class NaverMapsCrawler:
    """Selenium 기반 크롤러 (Chrome이 사용 가능한 환경에서만)"""

    def __init__(self):
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium이 사용할 수 없는 환경입니다.")

        self.options = Options()
        # Railway 환경에 최적화된 Chrome 옵션
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--disable-features=VizDisplayCompositor")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--remote-debugging-port=9222")
        self.options.add_argument("--disable-extensions")
        self.options.add_argument("--disable-plugins")
        self.options.add_argument("--disable-images")
        self.options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # 메모리 최적화
        self.options.add_argument("--max_old_space_size=4096")
        self.options.add_argument("--memory-pressure-off")

        self.driver = None
        self.wait = None
        self.processed_cafes = set()

    def start_driver(self):
        """Chrome driver 안전하게 초기화"""
        try:
            # ChromeDriver 경로 수정 시도
            try:
                service = Service(ChromeDriverManager().install())
                # 실제 chromedriver 바이너리 경로 찾기
                driver_path = service.path
                if 'THIRD_PARTY_NOTICES' in driver_path:
                    # 잘못된 경로인 경우 수정
                    driver_dir = os.path.dirname(driver_path)
                    actual_driver = os.path.join(driver_dir, 'chromedriver')
                    if os.path.exists(actual_driver):
                        service = Service(actual_driver)
                        logger.info(f"ChromeDriver 경로 수정: {actual_driver}")
                    else:
                        # chromedriver-linux64 폴더 내부 확인
                        linux_driver = os.path.join(driver_dir, 'chromedriver-linux64', 'chromedriver')
                        if os.path.exists(linux_driver):
                            service = Service(linux_driver)
                            logger.info(f"ChromeDriver 경로 수정: {linux_driver}")
                        else:
                            raise FileNotFoundError("ChromeDriver 바이너리를 찾을 수 없습니다.")

            except Exception as e:
                logger.error(f"ChromeDriver 설정 오류: {e}")
                raise

            self.driver = webdriver.Chrome(service=service, options=self.options)
            self.wait = WebDriverWait(self.driver, 15)
            logger.info("Chrome driver initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise

    def crawl_cafes(self, search_url: str, location: str, limit: int = 5) -> list:
        """Selenium 크롤링 (기존 로직)"""
        cafe_data = []
        try:
            self.start_driver()
            # 기존 크롤링 로직...
            logger.info("Selenium 크롤링 시작")
            return cafe_data
        except Exception as e:
            logger.error(f"Selenium 크롤링 실패: {e}")
            return cafe_data
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass

def save_to_supabase(cafes: List[Dict]):
    """카페 정보를 Supabase에 저장"""
    if not supabase:
        logger.error("Supabase 클라이언트가 초기화되지 않았습니다.")
        return

    try:
        saved_count = 0
        updated_count = 0

        for cafe in cafes:
            try:
                # 메뉴 아이템을 JSON 문자열로 변환
                menu_items_json = json.dumps(cafe["menu_items"], ensure_ascii=False) if cafe["menu_items"] else "[]"

                cafe_data = {
                    "name": cafe["name"],
                    "category": cafe["category"],
                    "address": cafe["address"],
                    "locationKeyword": cafe["locationKeyword"],
                    "business_district": cafe["business_district"],
                    "menu_items": menu_items_json,
                    "latitude": cafe.get("latitude"),
                    "longitude": cafe.get("longitude")
                }

                # 기존 데이터 확인
                existing = supabase.table('cafes').select("*").eq("name", cafe["name"]).eq("address", cafe["address"]).execute()

                if existing.data:
                    result = supabase.table('cafes').update(cafe_data).eq("name", cafe["name"]).eq("address", cafe["address"]).execute()
                    logger.info(f"Supabase 데이터 업데이트 성공: {cafe['name']}")
                    updated_count += 1
                else:
                    result = supabase.table('cafes').insert(cafe_data).execute()
                    logger.info(f"Supabase 새 데이터 저장 성공: {cafe['name']}")
                    saved_count += 1

            except Exception as e:
                logger.error(f"Supabase 개별 카페 저장 실패 ({cafe['name']}): {str(e)}")
                continue

        logger.info(f"Supabase 저장 완료 - 새로 저장: {saved_count}개, 업데이트: {updated_count}개")

    except Exception as e:
        logger.error(f"Supabase 전체 저장 프로세스 실패: {str(e)}")

def get_coords_from_address(address: str) -> Optional[Dict[str, float]]:
    """주소를 좌표로 변환"""
    if not KAKAO_API_KEY:
        logger.error("Kakao API 키가 설정되지 않았습니다.")
        return None
    try:
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"query": address}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['documents']:
            doc = data['documents'][0]
            return {"lat": float(doc['y']), "lon": float(doc['x'])}

        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data['documents']:
            doc = data['documents'][0]
            return {"lat": float(doc['y']), "lon": float(doc['x'])}

    except Exception as e:
        logger.error(f"주소 좌표 변환 실패: {address} - {e}")

    return None

def get_search_url(lat: float, lon: float) -> str:
    """좌표 기반 검색 URL 생성"""
    return f"https://map.naver.com/p/search/카페?c=15.00,0,0,0,dh&searchType=place&query=카페&lon={lon}&lat={lat}"

# Flask 라우트 정의
@app.route('/')
def home():
    return jsonify({
        "message": "Cafe Crawler API",
        "endpoints": {
            "crawl": "/crawl?lat=37.5665&lng=126.9780",
            "status": "/status"
        },
        "status": {
            "supabase": "연결됨" if supabase else "연결 실패",
            "kakao_api": "설정됨" if KAKAO_API_KEY else "미설정",
            "selenium": "사용 가능" if SELENIUM_AVAILABLE else "Requests 모드"
        }
    })

@app.route('/status')
def status():
    return jsonify({
        "status": "running",
        "message": "Cafe Crawler is ready",
        "services": {
            "supabase": "OK" if supabase else "ERROR",
            "kakao_api": "OK" if KAKAO_API_KEY else "ERROR",
            "crawler_mode": "Selenium" if SELENIUM_AVAILABLE else "Requests"
        }
    })

@app.route('/crawl')
def crawl():
    try:
        # 서비스 상태 확인
        if not supabase:
            return jsonify({
                "error": "Supabase 연결이 설정되지 않았습니다.",
                "details": "데이터베이스 환경 변수를 확인해주세요."
            }), 500

        if not KAKAO_API_KEY:
            return jsonify({
                "error": "Kakao API 키가 설정되지 않았습니다.",
                "details": "NEXT_PUBLIC_KAKAO_REST_API_KEY 환경 변수를 확인해주세요."
            }), 500

        # 쿼리 파라미터에서 좌표 가져오기
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)

        if not lat or not lng:
            return jsonify({
                "error": "lat과 lng 파라미터가 필요합니다.",
                "example": "/crawl?lat=37.5665&lng=126.9780"
            }), 400

        # 좌표 유효성 검증
        if not (33 <= lat <= 38) or not (125 <= lng <= 130):
            return jsonify({
                "error": "유효하지 않은 좌표입니다. 한국 영역 내의 좌표를 입력해주세요.",
                "provided": {"lat": lat, "lng": lng}
            }), 400

        logger.info(f"크롤링 시작: lat={lat}, lng={lng}")

        # 크롤링 방법 선택 (Requests 우선, Selenium 폴백)
        cafe_data = []
        crawler_used = "none"

        try:
            # Requests 기반 크롤링 시도
            requests_crawler = RequestsCrawler()
            cafe_data = requests_crawler.search_nearby_cafes(lat, lng, limit=8)
            crawler_used = "requests_kakao_api"
            logger.info(f"Requests 크롤링 성공: {len(cafe_data)}개 카페 수집")

        except Exception as e:
            logger.warning(f"Requests 크롤링 실패: {e}")

            # Selenium 크롤링 시도 (fallback)
            if SELENIUM_AVAILABLE:
                try:
                    selenium_crawler = NaverMapsCrawler()
                    search_url = get_search_url(lat, lng)
                    location_str = f"{lat:.5f},{lng:.5f}"
                    cafe_data = selenium_crawler.crawl_cafes(search_url, location_str, limit=5)
                    crawler_used = "selenium_naver"
                    logger.info(f"Selenium 크롤링 성공: {len(cafe_data)}개 카페 수집")
                except Exception as se:
                    logger.error(f"Selenium 크롤링도 실패: {se}")
                    crawler_used = "failed"
            else:
                logger.error("Selenium을 사용할 수 없어 크롤링 실패")
                crawler_used = "failed"

        # Supabase에 저장
        if cafe_data:
            save_to_supabase(cafe_data)
            logger.info(f"크롤링 완료: {len(cafe_data)}개 카페 데이터 저장됨")
        else:
            logger.warning("크롤링된 카페 데이터가 없습니다.")

        return jsonify({
            "success": True,
            "message": f"크롤링 완료: {len(cafe_data)}개 카페 수집",
            "data_count": len(cafe_data),
            "location": f"{lat:.5f},{lng:.5f}",
            "crawler_used": crawler_used,
            "details": [{"name": cafe["name"], "address": cafe["address"]} for cafe in cafe_data[:3]]
        })

    except Exception as e:
        logger.error(f"크롤링 중 치명적 오류: {e}", exc_info=True)
        return jsonify({
            "error": f"크롤링 중 오류가 발생했습니다: {str(e)}",
            "type": type(e).__name__
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Flask 앱 시작 - 포트: {port}")
    logger.info(f"크롤링 모드: {'Selenium + Requests' if SELENIUM_AVAILABLE else 'Requests Only'}")
    app.run(host='0.0.0.0', port=port, debug=False)