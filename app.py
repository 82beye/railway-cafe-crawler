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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import logging
from typing import List, Dict, Optional
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask 앱 초기화
app = Flask(__name__)

# 환경 변수 로드
load_dotenv()

# API 키 로드
KAKAO_API_KEY = os.getenv("NEXT_PUBLIC_KAKAO_REST_API_KEY")

# Supabase 클라이언트 초기화
supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
supabase_key = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

# Supabase 클라이언트 안전하게 초기화
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

# 검색할 장소 목록
SEARCH_LOCATIONS = [
    "광화문역", "종각역", "시청역", "을지로입구역",
    "강남역", "역삼역", "삼성중앙역", "선릉역", "테헤란로",
    "여의도역", "여의나루역", "국회의사당역",
    "삼성중앙역", "봉은사역", "코엑스",
    "디지털미디어시티역", "월드컵경기장역",
    "판교역", "정자역",
]

class NaverMapsCrawler:
    def __init__(self):
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
        self.options.add_argument("--disable-images")  # 이미지 로딩 비활성화로 속도 향상
        self.options.add_argument("--disable-javascript")  # 필요한 경우에만 활성화
        self.options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # 메모리 최적화
        self.options.add_argument("--max_old_space_size=4096")
        self.options.add_argument("--memory-pressure-off")

        self.driver = None
        self.wait = None
        self.processed_cafes = set()

    def start_driver(self):
        """Initialize the Chrome driver with configured options"""
        try:
            # webdriver-manager를 사용하여 ChromeDriver 자동 다운로드 및 설정
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=self.options)
            self.wait = WebDriverWait(self.driver, 15)  # 타임아웃 단축
            logger.info("Chrome driver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise

    def quit_driver(self):
        """Safely quit the Chrome driver"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Chrome driver closed successfully")
            except Exception as e:
                logger.warning(f"Error closing Chrome driver: {e}")

    def wait_and_find_element(self, by: By, selector: str, timeout: int = 15) -> Optional[webdriver.remote.webelement.WebElement]:
        """Wait for and find a single element with error handling"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element
        except TimeoutException:
            logger.warning(f"Timeout waiting for element: {selector}")
            return None
        except Exception as e:
            logger.error(f"Error finding element {selector}: {e}")
            return None

    def wait_for_iframe(self, iframe_id: str, timeout: int = 15) -> bool:
        """Wait for iframe to be present and available"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.ID, iframe_id))
            )
            logger.info(f"Found iframe: {iframe_id}")
            return True
        except TimeoutException:
            logger.warning(f"Iframe not found: {iframe_id}")
            return False
        except Exception as e:
            logger.error(f"Error waiting for iframe {iframe_id}: {e}")
            return False

    def switch_to_iframe(self, iframe_id: str, timeout: int = 15) -> bool:
        """Safely switch to an iframe with error handling"""
        try:
            self.driver.switch_to.default_content()
            time.sleep(1)  # 대기 시간 단축

            if self.wait_for_iframe(iframe_id):
                WebDriverWait(self.driver, timeout).until(
                    EC.frame_to_be_available_and_switch_to_it(iframe_id)
                )
                logger.info(f"Successfully switched to iframe: {iframe_id}")
                time.sleep(1)  # 대기 시간 단축
                return True
            return False
        except TimeoutException:
            logger.warning(f"Timeout switching to iframe: {iframe_id}")
            return False
        except Exception as e:
            logger.error(f"Error switching to iframe {iframe_id}: {e}")
            return False

    def get_menu_items(self) -> List[Dict[str, any]]:
        """Extract menu items from the current page with improved error handling"""
        menu_items = []
        try:
            menu_tabs = self.driver.find_elements(By.CSS_SELECTOR, "div.YYh8o a.tpj9w._tab-menu")
            menu_tab = None
            for tab in menu_tabs:
                try:
                    span_element = tab.find_element(By.CSS_SELECTOR, "span.veBoZ")
                    if span_element.text == "메뉴":
                        menu_tab = tab
                        break
                except:
                    continue

            if menu_tab:
                self.driver.execute_script("arguments[0].click();", menu_tab)
                logger.info("메뉴 탭 클릭 성공")
                time.sleep(2)  # 대기 시간 단축
            else:
                logger.warning("메뉴 탭을 찾지 못함")
                return menu_items

            menu_links = self.driver.find_elements(By.CSS_SELECTOR, "a.xPf1B")
            logger.info(f"발견된 메뉴 아이템 수: {len(menu_links)}")

            for idx, menu in enumerate(menu_links[:20]):  # 최대 20개로 제한
                try:
                    name = menu.find_element(By.CSS_SELECTOR, "span.lPzHi").text
                    try:
                        description = menu.find_element(By.CSS_SELECTOR, "div.kPogF").text
                    except:
                        description = ""

                    price_elem = menu.find_element(By.CSS_SELECTOR, "div.GXS1X")
                    price_text = price_elem.text.replace("원", "").replace(",", "").strip()

                    # 가격을 숫자로 변환 시도
                    try:
                        price = int(price_text) if price_text.isdigit() else 0
                    except:
                        price = 0

                    try:
                        img_url = menu.find_element(By.CSS_SELECTOR, "img.K0PDV").get_attribute("src")
                    except:
                        img_url = ""

                    menu_item = {
                        "name": name,
                        "description": description,
                        "price": price,
                        "image_url": img_url
                    }
                    menu_items.append(menu_item)
                    logger.info(f"메뉴 수집 {idx+1}: {name} - {price}원")

                except Exception as e:
                    logger.warning(f"메뉴 아이템 {idx+1} 파싱 오류: {e}")
                    continue

        except Exception as e:
            logger.warning(f"메뉴 정보 수집 중 오류: {e}")

        logger.info(f"총 {len(menu_items)}개 메뉴 수집 완료")
        return menu_items

    def switch_to_search_iframe(self, timeout: int = 15) -> bool:
        """동적으로 search 결과 iframe 탐색 및 진입"""
        self.driver.switch_to.default_content()
        time.sleep(1)
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                src = iframe.get_attribute("src")
                if src and "search" in src:
                    self.driver.switch_to.frame(iframe)
                    logger.info(f"search iframe 진입: {src}")
                    time.sleep(1)
                    return True
            logger.warning("search 관련 iframe을 찾지 못함")
            return False
        except Exception as e:
            logger.error(f"iframe 탐색 중 오류: {e}")
            return False

    def crawl_cafes(self, search_url: str, location: str, limit: int = 10) -> list:
        """특정 위치의 카페를 크롤링합니다."""
        cafe_data = []
        try:
            self.start_driver()
            self.driver.get(search_url)
            logger.info(f"검색 URL 진입: {search_url}")
            time.sleep(5)  # 대기 시간 단축

            if not self.switch_to_search_iframe():
                logger.error("search iframe 진입 실패")
                return cafe_data

            cafe_links = self.driver.find_elements(By.CSS_SELECTOR, "a.place_bluelink.N_KDL")
            if not cafe_links:
                logger.warning(f"{location}: 카페 리스트를 찾지 못함")
                return cafe_data

            logger.info(f"발견된 카페 수: {len(cafe_links)}, 처리할 카페 수: {min(len(cafe_links), limit)}")

            processed_count = 0
            for idx, cafe_link in enumerate(cafe_links[:limit]):
                try:
                    cafe_name = cafe_link.find_element(By.CSS_SELECTOR, "span.TYaxT").text

                    cafe_key = f"{cafe_name}_{location}"
                    if cafe_key in self.processed_cafes:
                        logger.info(f"중복 카페 건너뛰기: {cafe_name} ({location})")
                        continue

                    try:
                        category = cafe_link.find_element(By.CSS_SELECTOR, "span.KCMnt").text
                    except:
                        category = "카페"

                    logger.info(f"카페 {idx+1} 처리 중: {cafe_name}")
                    cafe_link.click()
                    time.sleep(2)  # 대기 시간 단축

                    self.driver.switch_to.default_content()
                    entry_iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    entry_found = False
                    for iframe in entry_iframes:
                        src = iframe.get_attribute("src")
                        if src and "entry" in src:
                            self.driver.switch_to.frame(iframe)
                            entry_found = True
                            time.sleep(1)
                            break

                    if not entry_found:
                        logger.warning(f"상세 entry iframe을 찾지 못함: {cafe_name}")
                        self.switch_to_search_iframe()
                        continue

                    address_elem = self.wait_and_find_element(By.CSS_SELECTOR, "span.LDgIH")
                    address = address_elem.text if address_elem else "주소 없음"

                    # 주소로부터 좌표 추출
                    coords = get_coords_from_address(address)

                    menu_items = self.get_menu_items()

                    cafe_info = {
                        "name": cafe_name,
                        "category": category,
                        "address": address,
                        "locationKeyword": location,
                        "menu_items": menu_items,
                        "business_district": self.get_business_district(location),
                        "latitude": coords['lat'] if coords else None,
                        "longitude": coords['lon'] if coords else None
                    }
                    cafe_data.append(cafe_info)
                    self.processed_cafes.add(cafe_key)
                    logger.info(f"수집 완료: {cafe_name} ({location}) - 메뉴 {len(menu_items)}개")

                    self.switch_to_search_iframe()
                    processed_count += 1

                except Exception as e:
                    logger.error(f"카페 {idx+1} 상세 수집 오류: {e}")
                    self.switch_to_search_iframe()
                    continue

            logger.info(f"총 {len(cafe_data)}개 카페 수집 완료 ({location})")
            return cafe_data

        except Exception as e:
            logger.error(f"크롤링 중 치명적 오류: {e}")
            return cafe_data
        finally:
            self.quit_driver()

    def get_business_district(self, location: str) -> str:
        """위치 정보를 기반으로 업무지구를 반환합니다."""
        if any(keyword in location for keyword in ["강남", "역삼", "선릉", "테헤란로"]):
            return "강남 업무지구"
        elif any(keyword in location for keyword in ["여의도", "여의나루", "국회"]):
            return "여의도 업무지구"
        elif any(keyword in location for keyword in ["광화문", "종각", "시청", "을지로"]):
            return "종로/광화문 업무지구"
        elif any(keyword in location for keyword in ["삼성중앙", "봉은사", "코엑스"]):
            return "삼성동 업무지구"
        elif any(keyword in location for keyword in ["디지털미디어시티", "월드컵"]):
            return "상암 업무지구"
        elif any(keyword in location for keyword in ["판교", "정자"]):
            return "판교 업무지구"
        else:
            return "기타"

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

                # 기존 데이터 확인 (이름과 주소로 중복 체크)
                existing = supabase.table('cafes').select("*").eq("name", cafe["name"]).eq("address", cafe["address"]).execute()

                if existing.data:
                    # 업데이트
                    result = supabase.table('cafes').update(cafe_data).eq("name", cafe["name"]).eq("address", cafe["address"]).execute()
                    logger.info(f"Supabase 데이터 업데이트 성공: {cafe['name']}")
                    updated_count += 1
                else:
                    # 새로 삽입
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
        # 주소 검색 API 시도
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"query": address}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['documents']:
            doc = data['documents'][0]
            return {"lat": float(doc['y']), "lon": float(doc['x'])}

        # 키워드 검색 API 시도
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data['documents']:
            doc = data['documents'][0]
            return {"lat": float(doc['y']), "lon": float(doc['x'])}

    except requests.exceptions.RequestException as e:
        logger.error(f"카카오 API 호출 오류: {e}")
    except (KeyError, IndexError, ValueError) as e:
        logger.error(f"주소 좌표 변환 실패: {address} - {e}")
    except Exception as e:
        logger.error(f"예상치 못한 오류: {address} - {e}")

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
            "kakao_api": "설정됨" if KAKAO_API_KEY else "미설정"
        }
    })

@app.route('/status')
def status():
    return jsonify({
        "status": "running",
        "message": "Cafe Crawler is ready",
        "services": {
            "supabase": "OK" if supabase else "ERROR",
            "kakao_api": "OK" if KAKAO_API_KEY else "ERROR"
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

        # 크롤링 실행
        crawler = NaverMapsCrawler()
        search_url = get_search_url(lat, lng)
        location_str = f"{lat:.5f},{lng:.5f}"

        # Railway 제한을 고려하여 limit 축소 및 타임아웃 설정
        cafe_data = crawler.crawl_cafes(search_url, location_str, limit=5)

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
            "location": location_str,
            "details": [{"name": cafe["name"], "address": cafe["address"]} for cafe in cafe_data[:3]]  # 처음 3개만 표시
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
    app.run(host='0.0.0.0', port=port, debug=False)