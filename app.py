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
from geopy.distance import geodesic

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

if not supabase_url or not supabase_key:
    logger.error("Supabase 환경 변수가 설정되지 않았습니다.")
else:
    supabase: Client = create_client(supabase_url, supabase_key)

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
        self.options.add_argument("--headless")  # Railway에서는 headless 모드 필수
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--remote-debugging-port=9222")
        self.options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        self.driver = None
        self.wait = None
        self.processed_cafes = set()

    def start_driver(self):
        """Initialize the Chrome driver with configured options"""
        try:
            # webdriver-manager를 사용하여 ChromeDriver 자동 다운로드 및 설정
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=self.options)
            self.wait = WebDriverWait(self.driver, 20)
            logger.info("Chrome driver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise

    def quit_driver(self):
        """Safely quit the Chrome driver"""
        if self.driver:
            self.driver.quit()
            logger.info("Chrome driver closed successfully")

    def wait_and_find_element(self, by: By, selector: str, timeout: int = 20) -> Optional[webdriver.remote.webelement.WebElement]:
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

    def wait_for_iframe(self, iframe_id: str, timeout: int = 20) -> bool:
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

    def switch_to_iframe(self, iframe_id: str, timeout: int = 20) -> bool:
        """Safely switch to an iframe with error handling"""
        try:
            self.driver.switch_to.default_content()
            time.sleep(2)

            if self.wait_for_iframe(iframe_id):
                WebDriverWait(self.driver, timeout).until(
                    EC.frame_to_be_available_and_switch_to_it(iframe_id)
                )
                logger.info(f"Successfully switched to iframe: {iframe_id}")
                time.sleep(2)
                return True
            return False
        except TimeoutException:
            logger.warning(f"Timeout switching to iframe: {iframe_id}")
            return False
        except Exception as e:
            logger.error(f"Error switching to iframe {iframe_id}: {e}")
            return False

    def get_menu_items(self) -> List[Dict[str, str]]:
        """Extract menu items from the current page"""
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
                time.sleep(3)
            else:
                logger.warning("메뉴 탭을 찾지 못함")
                return menu_items

            menu_links = self.driver.find_elements(By.CSS_SELECTOR, "a.xPf1B")
            for menu in menu_links:
                try:
                    name = menu.find_element(By.CSS_SELECTOR, "span.lPzHi").text
                    try:
                        description = menu.find_element(By.CSS_SELECTOR, "div.kPogF").text
                    except:
                        description = ""

                    price_elem = menu.find_element(By.CSS_SELECTOR, "div.GXS1X")
                    price = price_elem.text.replace("원", "").replace(",", "").strip()

                    try:
                        img_url = menu.find_element(By.CSS_SELECTOR, "img.K0PDV").get_attribute("src")
                    except:
                        img_url = ""

                    menu_items.append({
                        "name": name,
                        "description": description,
                        "price": price,
                        "image_url": img_url
                    })
                    logger.info(f"메뉴 수집: {name}")
                except Exception as e:
                    logger.warning(f"메뉴 아이템 파싱 오류: {e}")
                    continue

        except Exception as e:
            logger.warning(f"메뉴 정보 수집 중 오류: {e}")

        return menu_items

    def switch_to_search_iframe(self, timeout: int = 20) -> bool:
        """동적으로 search 결과 iframe 탐색 및 진입"""
        self.driver.switch_to.default_content()
        time.sleep(2)
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                src = iframe.get_attribute("src")
                if src and "search" in src:
                    self.driver.switch_to.frame(iframe)
                    logger.info(f"search iframe 진입: {src}")
                    time.sleep(2)
                    return True
            logger.warning("search 관련 iframe을 찾지 못함")
            return False
        except Exception as e:
            logger.error(f"iframe 탐색 중 오류: {e}")
            return False

    def crawl_cafes(self, lat: float, lng: float, limit: int = 10, max_distance_km: float = 2.0) -> List[Dict]:
        """네이버 지도에서 카페 정보를 크롤링합니다."""
        cafes = []
        try:
            # 좌표를 지역명으로 변환
            region_name = get_region_name_from_coords(lat, lng)
            if region_name:
                search_query = f"{region_name} 카페"
                logger.info(f"검색 쿼리: {search_query}")
            else:
                search_query = "카페"
                logger.warning("지역명 변환 실패, 기본 검색어 사용")
            
            # 네이버 지도 검색 URL 생성 (지역명 기반)
            search_url = f"https://map.naver.com/v5/search/{quote(search_query)}"
            logger.info(f"네이버 지도 검색 URL: {search_url}")
            
            self.start_driver()
            self.driver.get(search_url)
            time.sleep(7)

            if not self.switch_to_search_iframe():
                logger.error("search iframe 진입 실패")
                return cafes

            cafe_links = self.driver.find_elements(By.CSS_SELECTOR, "a.place_bluelink.N_KDL")
            if not cafe_links:
                logger.warning(f"카페 리스트를 찾지 못함")
                return cafes

            collected_count = 0
            for cafe_link in cafe_links:
                if collected_count >= limit:
                    break
                    
                try:
                    cafe_name = cafe_link.find_element(By.CSS_SELECTOR, "span.TYaxT").text

                    cafe_key = f"{cafe_name}_{lat}_{lng}"
                    if cafe_key in self.processed_cafes:
                        logger.info(f"중복 카페 건너뛰기: {cafe_name}")
                        continue

                    try:
                        category = cafe_link.find_element(By.CSS_SELECTOR, "span.KCMnt").text
                    except:
                        category = "카페"

                    cafe_link.click()
                    time.sleep(3)

                    self.driver.switch_to.default_content()
                    entry_iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    entry_found = False
                    for iframe in entry_iframes:
                        src = iframe.get_attribute("src")
                        if src and "entry" in src:
                            self.driver.switch_to.frame(iframe)
                            entry_found = True
                            time.sleep(2)
                            break

                    if not entry_found:
                        logger.warning(f"상세 entry iframe을 찾지 못함: {cafe_name}")
                        continue

                    address_elem = self.wait_and_find_element(By.CSS_SELECTOR, "span.LDgIH")
                    address = address_elem.text if address_elem else "주소 없음"

                    # 주소를 좌표로 변환
                    coords = get_coords_from_address(address)
                    
                    menu_items = self.get_menu_items()

                    cafe_info = {
                        "name": cafe_name,
                        "category": category,
                        "address": address,
                        "locationKeyword": region_name or "",
                        "menu_items": menu_items
                    }
                    
                    # 좌표 정보 추가 및 거리 계산
                    if coords:
                        cafe_info["latitude"] = coords["lat"]
                        cafe_info["longitude"] = coords["lon"]
                        
                        distance = calculate_distance(
                            lat, lng,
                            coords["lat"], coords["lon"]
                        )
                        cafe_info["distance_km"] = round(distance, 2)
                        
                        if distance <= max_distance_km:
                            cafes.append(cafe_info)
                            self.processed_cafes.add(cafe_key)
                            collected_count += 1
                            logger.info(f"카페 {collected_count}: {cafe_name} (거리: {distance:.2f}km) 수집 완료")
                        else:
                            logger.debug(f"카페 {cafe_name} 거리 초과 (거리: {distance:.2f}km > {max_distance_km}km)")
                    else:
                        # 좌표 정보가 없는 경우에도 수집
                        cafes.append(cafe_info)
                        self.processed_cafes.add(cafe_key)
                        collected_count += 1
                        logger.info(f"카페 {collected_count}: {cafe_name} (좌표 정보 없음) 수집 완료")

                    self.switch_to_search_iframe()

                except Exception as e:
                    logger.error(f"카페 상세 수집 오류: {e}")
                    self.switch_to_search_iframe()
                    continue

            logger.info(f"총 {len(cafes)}개 카페 수집 완료")
            return cafes

        except Exception as e:
            logger.error(f"크롤링 중 치명적 오류: {e}")
            return cafes
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
    try:
        for cafe in cafes:
            try:
                # 실제 Supabase 테이블 스키마에 맞게 구조 조정
                cafe_data = {
                    "name": cafe["name"],
                    "category": cafe.get("category", "카페"),
                    "address": cafe["address"],
                    "location": cafe.get("location", {}),
                    "latitude": cafe.get("latitude"),
                    "longitude": cafe.get("longitude"),
                    "locationKeyword": f'"{cafe.get("locationKeyword", "")}"',  # 따옴표 포함
                    "menu_items": json.dumps(cafe.get("menu_items", {}), ensure_ascii=False)
                }

                existing = supabase.table('cafes').select("*").eq("name", cafe["name"]).eq("address", cafe["address"]).execute()

                if existing.data:
                    result = supabase.table('cafes').update(cafe_data).eq("name", cafe["name"]).eq("address", cafe["address"]).execute()
                    logger.info(f"Supabase 데이터 업데이트 성공: {cafe['name']}")
                else:
                    result = supabase.table('cafes').insert(cafe_data).execute()
                    logger.info(f"Supabase 새 데이터 저장 성공: {cafe['name']}")

            except Exception as e:
                logger.error(f"Supabase 개별 카페 저장 실패 ({cafe['name']}): {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Supabase 전체 저장 프로세스 실패: {str(e)}")

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 간의 거리를 계산합니다 (단위: km)"""
    try:
        distance = geodesic((lat1, lon1), (lat2, lon2)).kilometers
        return distance
    except Exception as e:
        logger.error(f"거리 계산 오류: {e}")
        return float('inf')

def get_region_name_from_coords(lat: float, lon: float) -> Optional[str]:
    """좌표를 지역명으로 변환 (동 단위까지 포함)"""
    if not KAKAO_API_KEY:
        logger.error("Kakao API 키가 설정되지 않았습니다.")
        return None
    
    try:
        url = "https://dapi.kakao.com/v2/local/geo/coord2address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"x": lon, "y": lat}
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data['documents']:
            # 동 정보가 있는 주소를 우선 사용 (지번 주소 우선, 없으면 도로명 주소)
            address_info = data['documents'][0]
            region_name = None
            
            # 지번 주소에서 동 정보 확인
            if address_info.get('address'):
                region_2depth = address_info['address']['region_2depth_name']  # 구
                region_3depth = address_info['address'].get('region_3depth_name', '')  # 동
                if region_3depth:  # 동 정보가 있으면 사용
                    region_name = f"{region_2depth} {region_3depth}"
                else:
                    region_name = region_2depth
            
            # 지번 주소에 동 정보가 없으면 도로명 주소 확인
            if not region_3depth and address_info.get('road_address'):
                region_2depth = address_info['road_address']['region_2depth_name']  # 구
                region_3depth = address_info['road_address'].get('region_3depth_name', '')  # 동
                if region_3depth:  # 동 정보가 있으면 사용
                    region_name = f"{region_2depth} {region_3depth}"
                elif not region_name:  # 지번 주소도 없었다면
                    region_name = region_2depth
            
            if not region_name:
                return None
            
            logger.info(f"좌표 {lat}, {lon}을 지역명 '{region_name}'으로 변환")
            return region_name
        
        return None
    except Exception as e:
        logger.error(f"좌표-지역명 변환 오류: {e}")
        return None

def get_coords_from_address(address: str) -> Optional[Dict[str, float]]:
    """주소를 좌표로 변환"""
    if not KAKAO_API_KEY:
        logger.error("Kakao API 키가 설정되지 않았습니다.")
        return None
    try:
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"query": address}
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if data['documents']:
            doc = data['documents'][0]
            return {"lat": float(doc['y']), "lon": float(doc['x'])}

        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data['documents']:
            doc = data['documents'][0]
            return {"lat": float(doc['y']), "lon": float(doc['x'])}

    except requests.exceptions.RequestException as e:
        logger.error(f"카카오 API 호출 오류: {e}")
    except (KeyError, IndexError):
        logger.error(f"주소 좌표 변환 실패: {address}")
    return None



# Flask 라우트 정의
@app.route('/')
def home():
    return jsonify({
        "message": "Cafe Crawler API",
        "endpoints": {
            "crawl": "/crawl?lat=37.5665&lng=126.9780",
            "status": "/status"
        }
    })

@app.route('/status')
def status():
    return jsonify({
        "status": "running",
        "message": "Cafe Crawler is ready"
    })

@app.route('/crawl', methods=['GET'])
def crawl():
    """카페 크롤링 API"""
    try:
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        limit = request.args.get('limit', default=10, type=int)
        max_distance = request.args.get('max_distance', default=2.0, type=float)
        
        if lat is None or lng is None:
            return jsonify({"error": "lat과 lng 파라미터가 필요합니다."}), 400
        
        logger.info(f"크롤링 요청: 위도={lat}, 경도={lng}, 제한={limit}, 최대거리={max_distance}km")
        
        # 크롤러 인스턴스 생성
        crawler = NaverMapsCrawler()
        
        # 카페 크롤링 실행
        cafes = crawler.crawl_cafes(lat, lng, limit=limit, max_distance_km=max_distance)
        
        if not cafes:
            return jsonify({"message": "수집된 카페가 없습니다.", "data": []}), 200
        
        # Supabase에 저장
        save_to_supabase(cafes)
        
        return jsonify({
            "message": f"{len(cafes)}개의 카페 정보를 수집했습니다.",
            "data": cafes,
            "search_location": {"lat": lat, "lng": lng},
            "max_distance_km": max_distance
        }), 200
        
    except Exception as e:
        logger.error(f"크롤링 API 오류: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)