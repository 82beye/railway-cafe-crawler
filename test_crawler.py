#!/usr/bin/env python3
"""
Railway 카페 크롤러 테스트 스크립트
로컬 또는 배포된 환경에서 크롤링 및 저장 기능을 테스트
"""

import requests
import json
import time
import sys
from typing import Dict, Any

def test_crawler_api(base_url: str = "http://localhost:5000") -> None:
    """크롤러 API 테스트"""

    print(f"🧪 Railway 카페 크롤러 테스트 시작")
    print(f"🔗 테스트 URL: {base_url}")
    print("=" * 50)

    # 1. 상태 확인
    print("\n1️⃣ 서비스 상태 확인...")
    try:
        response = requests.get(f"{base_url}/status", timeout=10)
        if response.status_code == 200:
            status_data = response.json()
            print("✅ 서비스 정상 작동")
            print(f"   - Supabase: {status_data.get('services', {}).get('supabase', 'Unknown')}")
            print(f"   - Kakao API: {status_data.get('services', {}).get('kakao_api', 'Unknown')}")
            print(f"   - 크롤링 모드: {status_data.get('services', {}).get('crawler_mode', 'Unknown')}")
        else:
            print(f"❌ 상태 확인 실패: HTTP {response.status_code}")
            return
    except Exception as e:
        print(f"❌ 상태 확인 오류: {e}")
        return

    # 2. 홈 엔드포인트 확인
    print("\n2️⃣ 홈 엔드포인트 확인...")
    try:
        response = requests.get(f"{base_url}/", timeout=10)
        if response.status_code == 200:
            home_data = response.json()
            print("✅ 홈 엔드포인트 정상")
            print(f"   - 메시지: {home_data.get('message', 'Unknown')}")
        else:
            print(f"❌ 홈 엔드포인트 오류: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ 홈 엔드포인트 오류: {e}")

    # 3. 크롤링 테스트 (서울 강남역 근처)
    print("\n3️⃣ 카페 크롤링 테스트...")
    test_locations = [
        {"name": "강남역", "lat": 37.497952, "lng": 127.027619},
        {"name": "홍대입구역", "lat": 37.557527, "lng": 126.925211},
        {"name": "명일동", "lat": 37.5488512, "lng": 127.1496704}
    ]

    for location in test_locations:
        print(f"\n   📍 {location['name']} 테스트...")
        try:
            crawl_url = f"{base_url}/crawl?lat={location['lat']}&lng={location['lng']}"
            print(f"   🔗 요청 URL: {crawl_url}")

            start_time = time.time()
            response = requests.get(crawl_url, timeout=60)  # 1분 타임아웃
            end_time = time.time()

            print(f"   ⏱️ 응답 시간: {end_time - start_time:.2f}초")

            if response.status_code == 200:
                result = response.json()
                print_crawl_result(result, location['name'])
                break  # 첫 번째 성공하면 다른 위치는 테스트하지 않음
            else:
                print(f"   ❌ 크롤링 실패: HTTP {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   ❌ 오류 메시지: {error_data.get('error', 'Unknown error')}")
                except:
                    print(f"   ❌ 응답 파싱 실패")

        except requests.exceptions.Timeout:
            print(f"   ⏰ 크롤링 타임아웃 (60초 초과)")
        except Exception as e:
            print(f"   ❌ 크롤링 오류: {e}")

    print("\n" + "=" * 50)
    print("🏁 테스트 완료")

def print_crawl_result(result: Dict[str, Any], location_name: str) -> None:
    """크롤링 결과 출력"""
    print(f"   📊 {location_name} 크롤링 결과:")
    print(f"   - 전체 성공: {'✅' if result.get('success') else '❌'}")
    print(f"   - 수집 카페 수: {result.get('data_count', 0)}개")
    print(f"   - 크롤링 방법: {result.get('crawler_used', 'Unknown')}")

    # 데이터베이스 저장 결과
    db_save = result.get('database_save', {})
    if db_save:
        print(f"   - DB 저장 성공: {'✅' if db_save.get('success') else '❌'}")
        print(f"   - 새로 저장: {db_save.get('saved_count', 0)}개")
        print(f"   - 업데이트: {db_save.get('updated_count', 0)}개")
        print(f"   - 실패: {db_save.get('failed_count', 0)}개")
        print(f"   - 저장 메시지: {db_save.get('message', '')}")

        if db_save.get('errors'):
            print(f"   - 오류 목록:")
            for error in db_save.get('errors', [])[:3]:  # 최대 3개만 표시
                print(f"     • {error}")

    # 수집된 카페 목록
    details = result.get('details', [])
    if details:
        print(f"   - 수집된 카페 예시:")
        for i, cafe in enumerate(details[:3], 1):
            print(f"     {i}. {cafe.get('name', 'Unknown')} ({cafe.get('address', 'Unknown')})")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Railway 카페 크롤러 테스트")
    parser.add_argument(
        "--url",
        default="http://localhost:5000",
        help="테스트할 서버 URL (기본값: http://localhost:5000)"
    )

    args = parser.parse_args()

    # Railway 배포 URL 예시
    if args.url == "railway":
        args.url = "https://railway-cafe-crawler-production.up.railway.app"
        print("🚂 Railway 배포 환경 테스트 모드")

    test_crawler_api(args.url)