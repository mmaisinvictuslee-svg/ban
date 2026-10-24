# ============================================================
# API 키 직접 입력 위치 (두 따옴표 안에 본인의 키를 입력하세요)
# 개인 PC용입니다. 실제 키가 들어 있는 이 파일을 공개 GitHub에 올리지 마세요.
# 공개 배포에서는 아래 값을 빈칸으로 두고 Streamlit Settings → Secrets를 사용하세요.
# 이미 Secrets나 설정 도우미에 키를 등록했다면 아래 두 줄은 그대로 두면 됩니다.
# ============================================================
ADMIN_API_KEY = "QzAjtfdIGZxHaen63PZDjzL0EU2C6L59A2Wgp4W6bOVwmTsBBYZxx8A4H398SG7MlVmtLPyio0T+a3qp4DifKw=="
KAKAO_REST_API_KEY = "8cca2475c3e669ff863cce9addb93925"

import os
import html
import math
import random
import re
import hashlib
import json
from datetime import time as trip_clock_time
from pathlib import Path
import requests
import pandas as pd
import streamlit as st
import folium

from streamlit_folium import st_folium


# ============================================================
# 1. 기본 설정
# ============================================================

st.set_page_config(
    page_title="VillageON | 전국 지역 활성화 플랫폼",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 2. API KEY 안전하게 읽기
# ============================================================

def load_secret_safely(name):
    """코드에 직접 설정한 값부터 읽고, 없으면 기존 서버 설정을 사용합니다."""
    direct = {"ADMIN_API_KEY": ADMIN_API_KEY, "KAKAO_REST_API_KEY": KAKAO_REST_API_KEY}
    value = direct.get(name, "")
    if isinstance(value, str) and value.strip():
        return value.strip()
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    if isinstance(value, str) and value.strip():
        return value.strip()
    value = os.environ.get(name, "")
    if isinstance(value, str) and value.strip():
        return value.strip()
    try:
        settings_path = Path(__file__).resolve().parent / ".streamlit" / "villageon_keys.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        value = settings.get(name, "") if isinstance(settings, dict) else ""
    except (OSError, ValueError, TypeError):
        value = ""
    return value.strip() if isinstance(value, str) else ""




# ============================================================
# 3. 전국 시도 기본 좌표
# ============================================================

SIDO_COORDS = {
    "서울특별시": (37.5665, 126.9780),
    "부산광역시": (35.1796, 129.0756),
    "대구광역시": (35.8714, 128.6014),
    "인천광역시": (37.4563, 126.7052),
    "광주광역시": (35.1595, 126.8526),
    "대전광역시": (36.3504, 127.3845),
    "울산광역시": (35.5384, 129.3114),
    "세종특별자치시": (36.4800, 127.2890),
    "경기도": (37.4138, 127.5183),
    "강원특별자치도": (37.8228, 128.1555),
    "충청북도": (36.8000, 127.7000),
    "충청남도": (36.5184, 126.8000),
    "전북특별자치도": (35.7175, 127.1530),
    "전라남도": (34.8679, 126.9910),
    "경상북도": (36.4919, 128.8889),
    "경상남도": (35.4606, 128.2132),
    "제주특별자치도": (33.4890, 126.4983),
}


# ============================================================
# 4. 카카오 카테고리 코드
# ============================================================

CATEGORY_CODES = {
    "맛집": "FD6",
    "카페": "CE7",
    "관광지": "AT4",
    "숙박": "AD5",
    "학교": "SC4",
    "공원": "AT4",
}


CATEGORY_ICONS = {
    "맛집": "🍚",
    "카페": "☕",
    "관광지": "🏞️",
    "숙박": "🏨",
    "학교": "🏫",
    "축제": "🎉",
    "공원": "🌳",
    "문화": "🎭",
    "체험": "🎨",
}


# ============================================================
# 5. 행정안전부 API
# ============================================================

ADMIN_URL = (
    "https://apis.data.go.kr/1741000/"
    "StanReginCd/getStanReginCdList"
)


# ============================================================
# 6. 행정안전부 전국 행정구역 데이터
# ============================================================



class AdminRegionLoadError(ValueError):
    """전국 목록을 끝까지 검증하지 못했을 때 표시할, 키가 없는 오류."""


_ADMIN_COLUMNS = [
    "region_code", "sido_code", "sigungu_code", "eup_code", "li_code",
    "region_name", "order", "remark", "high_code", "low_name", "created",
]
_REGION_COLUMNS = ["sido", "sigungu", "eupmyeondong", "region_code"]
_ADMIN_SIDO_ALIASES = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
}


def _admin_text(value):
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return ""
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _admin_field(row, *names):
    for name in names:
        value = _admin_text(row.get(name))
        if value:
            return value
    return ""


def _admin_code(value, width=10):
    text = _admin_text(value)
    if re.fullmatch(r"[0-9]+\.0+", text):
        text = text.split(".", 1)[0]
    if not text.isascii() or not text.isdigit() or len(text) > width:
        return ""
    # 법정동 코드는 10자리 전체가 필요합니다. 하위 구분 코드는 0을 보충합니다.
    if width == 10 and len(text) != width:
        return ""
    return text.zfill(width)


def _admin_total(value):
    text = _admin_text(value).replace(",", "")
    if not re.fullmatch(r"[0-9]+", text):
        raise AdminRegionLoadError(
            "행정안전부 API의 전체 건수(totalCount)가 올바르지 않습니다. 잠시 후 다시 불러와 주세요."
        )
    return int(text)


def _admin_metadata(node, depth=0):
    """대량의 row 배열은 건너뛰고 head/header의 건수와 처리 코드를 읽습니다."""
    totals, codes = [], []
    if depth > 8:
        raise AdminRegionLoadError("행정안전부 API의 응답 구조를 확인할 수 없습니다.")
    if isinstance(node, list):
        for item in node:
            child_totals, child_codes = _admin_metadata(item, depth + 1)
            totals.extend(child_totals)
            codes.extend(child_codes)
    elif isinstance(node, dict):
        for key, value in node.items():
            normalized_key = str(key).lower().replace("_", "")
            if normalized_key in {"totalcount", "listtotalcount"}:
                totals.append(_admin_total(value))
            elif normalized_key == "resultcode":
                code = _admin_text(value).upper()
                if code:
                    codes.append(code)
            elif normalized_key not in {"row", "rows", "item", "items"}:
                if isinstance(value, (dict, list)):
                    child_totals, child_codes = _admin_metadata(value, depth + 1)
                    totals.extend(child_totals)
                    codes.extend(child_codes)
    return totals, codes


def _admin_row_values(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if not value:
            return []
        for key in ("item", "row", "rows"):
            if key in value:
                return _admin_row_values(value[key])
        return [value]
    raise AdminRegionLoadError(
        "행정안전부 API의 지역 목록 형식이 올바르지 않습니다. 전체 목록을 다시 불러와 주세요."
    )


def _admin_find_rows(node, depth=0):
    if depth > 8:
        raise AdminRegionLoadError("행정안전부 API의 응답 구조를 확인할 수 없습니다.")
    if isinstance(node, list):
        found = []
        present = False
        for item in node:
            result = _admin_find_rows(item, depth + 1)
            if result is not None:
                present = True
                found.extend(result)
        return found if present else None
    if isinstance(node, dict):
        for key in ("row", "rows", "items", "item"):
            if key in node:
                return _admin_row_values(node[key])
        for key in ("StanReginCd", "response", "body", "data", "result"):
            if key in node:
                result = _admin_find_rows(node[key], depth + 1)
                if result is not None:
                    return result
    return None


def _admin_decode_payload(payload):
    if not isinstance(payload, dict):
        raise AdminRegionLoadError("행정안전부 API가 올바른 JSON 객체를 반환하지 않았습니다.")
    totals, codes = _admin_metadata(payload)
    success_codes = {"INFO-0", "INFO-000", "00", "0000", "0", "200", "SUCCESS", "OK"}
    no_data_codes = {"INFO-200", "03"}
    if any(code not in success_codes | no_data_codes for code in codes):
        # API 응답 원문에는 인증키가 포함될 수 있어 메시지나 URL을 출력하지 않습니다.
        raise AdminRegionLoadError(
            "행정안전부 API가 요청을 정상 처리하지 못했습니다. 해당 API의 활용신청 승인, "
            "Decoding 인증키, 일일 호출 한도를 확인해 주세요."
        )
    rows = _admin_find_rows(payload)
    if not totals:
        if codes and any(code in no_data_codes for code in codes) and not rows:
            return [], 0
        raise AdminRegionLoadError(
            "행정안전부 API 응답에 전체 건수(totalCount)가 없어 전국 목록의 완전성을 확인할 수 없습니다."
        )
    if len(set(totals)) != 1:
        raise AdminRegionLoadError("행정안전부 API 응답의 전체 건수가 서로 다릅니다. 다시 불러와 주세요.")
    total = totals[0]
    if any(code in no_data_codes for code in codes) and (total or rows):
        raise AdminRegionLoadError("행정안전부 API의 처리 결과와 지역 건수가 일치하지 않습니다.")
    if rows is None:
        if total == 0:
            return [], 0
        raise AdminRegionLoadError("행정안전부 API 응답에 지역 목록이 없습니다. 다시 불러와 주세요.")
    if not all(isinstance(row, dict) for row in rows):
        raise AdminRegionLoadError("행정안전부 API 지역 목록에 잘못된 항목이 포함돼 있습니다.")
    return rows, total


def _admin_normalize_record(row):
    code = _admin_code(_admin_field(
        row, "region_cd", "region_code", "locatjumin_cd", "locatjijuk_cd"
    ))
    name = " ".join(_admin_field(row, "locatadd_nm", "region_name", "locataddNm").split())
    if not code or code == "0000000000" or not name:
        raise AdminRegionLoadError(
            "행정안전부 API 지역 항목의 법정동 코드 또는 지역명이 누락되거나 잘못됐습니다. "
            "불완전한 목록 대신 전체 목록을 다시 불러와 주세요."
        )
    result = {
        "region_code": code,
        "region_name": name,
        "sido_code": _admin_code(_admin_field(row, "sido_cd", "sido_code"), 2) or code[:2],
        "sigungu_code": _admin_code(_admin_field(row, "sgg_cd", "sigungu_code"), 3) or code[2:5],
        "eup_code": _admin_code(_admin_field(row, "umd_cd", "eup_code"), 3) or code[5:8],
        "li_code": _admin_code(_admin_field(row, "ri_cd", "li_code"), 2) or code[8:],
        "order": _admin_field(row, "locat_order", "order"),
        "remark": _admin_field(row, "locat_rm", "remark"),
        "high_code": _admin_field(row, "locathigh_cd", "high_code"),
        "low_name": _admin_field(row, "locallow_nm", "low_name"),
        "created": _admin_field(row, "adpt_de", "created"),
    }
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def load_admin_regions(api_key):
    """반환된 totalCount까지 모든 페이지를 검증한 경우에만 전국 목록을 캐시합니다."""
    if not _admin_text(api_key):
        return pd.DataFrame(columns=_ADMIN_COLUMNS)
    all_rows, seen_codes = [], set()
    expected_total = None
    for page in range(1, 1001):
        params = {
            "ServiceKey": str(api_key).strip(),
            "pageNo": page,
            "numOfRows": 1000,
            "type": "json",
        }
        try:
            response = requests.get(ADMIN_URL, params=params, timeout=(5, 20))
        except requests.Timeout:
            raise AdminRegionLoadError(
                f"전국 지역 목록 {page}페이지를 불러오다가 시간이 초과됐습니다. "
                "일부 지역만 표시하지 않도록 중단했습니다. 다시 불러와 주세요."
            ) from None
        except requests.RequestException:
            raise AdminRegionLoadError(
                f"전국 지역 목록 {page}페이지에 연결하지 못했습니다. 인터넷 연결을 확인하고 다시 불러와 주세요."
            ) from None
        if response.status_code in (401, 403):
            raise AdminRegionLoadError(
                "행정안전부 API 인증이 거절됐습니다. 활용신청 승인 여부와 Decoding 인증키를 확인해 주세요."
            )
        if response.status_code != 200:
            raise AdminRegionLoadError(
                f"전국 지역 목록 {page}페이지를 서버에서 받지 못했습니다. 잠시 후 다시 불러와 주세요."
            )
        try:
            payload = response.json()
        except (ValueError, TypeError):
            raise AdminRegionLoadError(
                "행정안전부 API가 JSON 대신 다른 형식의 응답을 보냈습니다. "
                "활용신청 승인 여부와 Decoding 인증키를 확인해 주세요."
            ) from None
        rows, total = _admin_decode_payload(payload)
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise AdminRegionLoadError(
                "불러오는 동안 전국 지역 목록의 전체 건수가 변경됐습니다. 최신 목록을 다시 불러와 주세요."
            )
        if not rows and len(all_rows) != expected_total:
            raise AdminRegionLoadError(
                f"전국 지역 목록 {page}페이지가 비어 있어 전체 목록을 완성하지 못했습니다. 다시 불러와 주세요."
            )
        for row in rows:
            normalized = _admin_normalize_record(row)
            if normalized["region_code"] in seen_codes:
                raise AdminRegionLoadError(
                    "행정안전부 API 페이지에 동일한 법정동 코드가 중복돼 전체 목록을 확인할 수 없습니다. "
                    "잠시 후 다시 불러와 주세요."
                )
            seen_codes.add(normalized["region_code"])
            all_rows.append(normalized)
        if len(all_rows) > expected_total:
            raise AdminRegionLoadError("행정안전부 API의 전체 건수와 실제 받은 건수가 다릅니다. 다시 불러와 주세요.")
        if len(all_rows) == expected_total:
            result = pd.DataFrame(all_rows, columns=_ADMIN_COLUMNS)
            result.attrs.update({"complete": True, "total_count": expected_total, "pages_loaded": page})
            return result
    raise AdminRegionLoadError(
        "전국 지역 목록의 페이지 수가 예상 범위를 넘어 불러오기를 중단했습니다. 전체 목록을 다시 불러와 주세요."
    )


def split_region_name(name):
    """법정동 주소에서 시+구를 보존하고, 리는 읍·면 수준으로 묶습니다."""
    parts = _admin_text(name).split()
    if not parts:
        return "", "", ""
    sido = _ADMIN_SIDO_ALIASES.get(parts[0], parts[0])
    if sido not in SIDO_COORDS:
        return "", "", ""
    remainder = parts[1:]
    if sido == "세종특별자치시":
        # 세종에는 시군구 중간 계층을 만들지 않습니다.
        return sido, "", remainder[0] if remainder else ""
    sigungu_parts = []
    while remainder and remainder[0].endswith(("시", "군", "구")):
        sigungu_parts.append(remainder.pop(0))
    if not sigungu_parts:
        return sido, "", ""
    # '세종로', '종로1가'처럼 이름이 동으로 끝나지 않는 법정동도 유지합니다.
    eupmyeondong = remainder[0] if remainder else ""
    return sido, " ".join(sigungu_parts), eupmyeondong


def build_region_dataframe(admin_df):
    """실제 선택 가능한 읍·면·동만 반환하고, 리/상위 집계 행 중복을 제거합니다."""
    if not isinstance(admin_df, pd.DataFrame) or admin_df.empty:
        return pd.DataFrame(columns=_REGION_COLUMNS)
    selected = {}
    for raw in admin_df.to_dict("records"):
        name = _admin_field(raw, "region_name", "locatadd_nm", "locataddNm")
        sido, sigungu, eup = split_region_name(name)
        if not sido or not eup or (not sigungu and sido != "세종특별자치시"):
            continue
        # 명확하게 폐지로 표시된 행만 제외합니다. 일반 비고는 추측해 해석하지 않습니다.
        if _admin_field(raw, "remark", "locat_rm") in {"폐지", "폐지됨", "말소"}:
            continue
        raw_code = _admin_code(_admin_field(
            raw, "region_cd", "region_code", "locatjumin_cd", "locatjijuk_cd"
        ))
        if not raw_code:
            continue
        # 법정리의 끝 2자리를 제거해 해당 읍/면/동의 법정동 코드로 올립니다.
        parent_code = raw_code[:8] + "00"
        identity = (sido, sigungu, eup)
        candidate = {
            "sido": sido, "sigungu": sigungu, "eupmyeondong": eup,
            "region_code": parent_code,
        }
        prior = selected.get(identity)
        if prior is None or raw_code.endswith("00"):
            selected[identity] = candidate
    if not selected:
        return pd.DataFrame(columns=_REGION_COLUMNS)
    return pd.DataFrame(selected.values(), columns=_REGION_COLUMNS).sort_values(
        ["sido", "sigungu", "eupmyeondong"]
    ).reset_index(drop=True)


def choose_random_region(regions, current=None):
    """시도 → 시군구 → 읍면동을 순서대로 추첨해 연결된 실제 지역 한 행을 반환합니다."""
    if isinstance(regions, pd.DataFrame):
        if not set(_REGION_COLUMNS).issubset(regions.columns):
            return None
        candidates = regions[_REGION_COLUMNS].copy()
    elif isinstance(regions, (list, tuple)) and regions:
        if not all(isinstance(row, dict) for row in regions):
            return None
        candidates = pd.DataFrame(regions)
        if not set(_REGION_COLUMNS).issubset(candidates.columns):
            return None
        candidates = candidates[_REGION_COLUMNS].copy()
    else:
        return None
    for column in _REGION_COLUMNS:
        candidates[column] = candidates[column].map(_admin_text)
    candidates = candidates[
        candidates["sido"].ne("")
        & candidates["eupmyeondong"].ne("")
        & candidates["region_code"].ne("")
        & (candidates["sigungu"].ne("") | candidates["sido"].eq("세종특별자치시"))
    ].drop_duplicates(["sido", "sigungu", "eupmyeondong"])
    if candidates.empty:
        return None
    identity_columns = ["sido", "sigungu", "eupmyeondong"]
    if isinstance(current, (dict, pd.Series)):
        identity = tuple(_admin_text(current.get(column)) for column in identity_columns)
    elif isinstance(current, (list, tuple)) and len(current) >= 3:
        identity = tuple(_admin_text(value) for value in current[:3])
    else:
        identity = None
    if identity is not None:
        is_current = pd.Series(True, index=candidates.index)
        for column, value in zip(identity_columns, identity):
            is_current &= candidates[column].eq(value)
        alternatives = candidates.loc[~is_current]
        if not alternatives.empty:
            candidates = alternatives
    picker = random.SystemRandom()
    sido = picker.choice(sorted(candidates["sido"].unique().tolist()))
    candidates = candidates[candidates["sido"].eq(sido)]
    sigungu = picker.choice(sorted(candidates["sigungu"].unique().tolist()))
    candidates = candidates[candidates["sigungu"].eq(sigungu)]
    result = picker.choice(candidates.to_dict("records"))
    return {column: str(result[column]) for column in _REGION_COLUMNS}


# ============================================================
# 8. 카카오 API 공통 오류 표시
# ============================================================

def kakao_error_message(response):
    # 응답 원문이나 요청 URL 대신 사용자가 확인할 수 있는 안내만 표시합니다.
    if response.status_code in (401, 403):
        return "카카오 REST API 키와 Local API 사용 권한을 확인해 주세요."
    if response.status_code == 429:
        return "카카오 API 사용 한도에 도달했어요. 사용량을 확인하고 잠시 후 다시 시도해 주세요."
    if response.status_code >= 500:
        return "카카오 서버에서 정상 응답을 받지 못했어요. 잠시 후 다시 시도해 주세요."
    return "카카오 요청을 처리하지 못했어요. API 키·권한과 검색 조건을 확인해 주세요."


# ============================================================
# 9. 카카오 주소 검색
# ============================================================

@st.cache_data(ttl=86400, show_spinner=False)
def kakao_address_search(
    address,
    api_key,
):

    if not api_key or not address:
        return None

    url = (
        "https://dapi.kakao.com/v2/local/"
        "search/address.json"
    )

    headers = {
        "Authorization": f"KakaoAK {api_key}"
    }

    params = {
        "query": address,
        "size": 1,
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=10,
        )

        if response.status_code != 200:
            return None

        data = response.json()

        documents = data.get(
            "documents",
            [],
        )

        if not documents:
            return None

        item = documents[0]

        return {
            "lat": float(item["y"]),
            "lon": float(item["x"]),
        }

    except Exception:
        return None


# ============================================================
# 10. 선택 지역 좌표
# ============================================================

def resolve_region_location(sido, sigungu, eup, api_key):
    """선택한 읍면동 좌표인지, 시도 표시용 대체 좌표인지 구분합니다."""
    full_address = " ".join(str(part).strip() for part in (sido, sigungu, eup) if part)
    if api_key and full_address:
        # 세종은 중간 시군구가 없어도 '세종특별자치시 보람동'을 그대로 검색합니다.
        result = kakao_address_search(full_address, api_key)
        if result:
            try:
                lat, lon = float(result["lat"]), float(result["lon"])
                if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
                    return {"lat": lat, "lon": lon, "coordinates_verified": True}
            except (KeyError, TypeError, ValueError):
                pass
    lat, lon = SIDO_COORDS.get(sido, (36.5, 127.8))
    return {"lat": lat, "lon": lon, "coordinates_verified": False}


def get_region_coordinate(sido, sigungu, eup, api_key):
    result = resolve_region_location(sido, sigungu, eup, api_key)
    return result["lat"], result["lon"]


# ============================================================
# 11. 카카오 키워드 검색: 전체 지역명과 실제 좌표를 사용한 최대 3페이지 조회
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def kakao_keyword_search(query, lat, lon, api_key, category_code=None, sort="accuracy"):
    """기존 추천·예산 코드에서 쓰는 두 항목 반환 인터페이스를 유지합니다."""
    documents, error, _ = kakao_keyword_search_detailed(query, lat, lon, api_key, category_code, sort)
    return documents, error



# ============================================================
# 12. 카카오 결과 DataFrame
# ============================================================

def kakao_results_dataframe(results):
    rows = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "place_id": _data_text(item.get("id")),
            "name": _data_text(item.get("place_name")) or "이름 정보 없음",
            "category": _data_text(item.get("category_name")) or "분류 정보 없음",
            "address": _data_text(item.get("road_address_name")) or _data_text(item.get("address_name")),
            "phone": _data_text(item.get("phone")), "distance": _data_text(item.get("distance")),
            "lat": _data_text(item.get("y")), "lon": _data_text(item.get("x")),
            "url": _data_text(item.get("place_url")),
        })
    return _data_deduplicate_frame(pd.DataFrame(rows))



# ============================================================
# 13. 지역 장소 데이터 수집
# 핵심 수정:
# 각 카테고리를 지역명으로 검색하지 않는다.
# 예:
# 가평군 + 맛집
# X
# 가평군 좌표 + 맛집(FD6)
# O
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def collect_local_data(sido, sigungu, eup, lat, lon, api_key):
    data = {}
    location = " ".join(_data_text(part) for part in (sido, sigungu, eup) if _data_text(part))
    if not api_key or not location:
        return data
    for category in _data_categories():
        query = f"{location} {category}"
        code = CATEGORY_CODES.get(category)
        results, error, search_meta = kakao_keyword_search_detailed(query, lat, lon, api_key, code)
        attempts = [dict(search_meta)]
        # 정상 빈 응답에만 분류 필터를 풀어 한 번 더 검색합니다. 인증 오류를 반복하지 않습니다.
        if not results and code and error is None and search_meta["status"] == "empty":
            results, error, search_meta = kakao_keyword_search_detailed(query, lat, lon, api_key, None)
            attempts.append(dict(search_meta))
        frame = kakao_results_dataframe(results)
        meta = dict(search_meta)
        for field in ("request_count", "success_count", "error_count", "pages_fetched", "raw_count", "duplicates_removed"):
            meta[field] = sum(attempt.get(field, 0) for attempt in attempts)
        meta["unique_count"] = len(frame)
        meta["attempt_count"] = len(attempts)
        meta["category_filter"] = code if len(attempts) == 1 else None
        frame.attrs.update({
            "search_meta": meta, "search_attempts": attempts,
            "api_request_count": meta["request_count"],
            "api_success_count": meta["success_count"],
            "api_error_count": meta["error_count"],
        })
        if error:
            frame.attrs["api_error"] = error
        data[category] = frame
    return data



# ============================================================
# 14. 지역 분석
# ============================================================





# ============================================================
# 15. 지역 이름
# ============================================================

def location_text(region):

    parts = [
        region.get("sido", ""),
        region.get("sigungu", ""),
        region.get("eup", ""),
    ]

    return " ".join(
        [
            str(x)
            for x in parts
            if x
        ]
    )


# ============================================================
# 16. 지도
# ============================================================

def make_map(region, places=None):
    center = _map_coordinates(region.get("lat"), region.get("lon"))
    verified = center is not None and bool(region.get("coordinates_verified"))
    if center is None:
        center = SIDO_COORDS.get(region.get("sido"), SIDO_COORDS["서울특별시"])
    village_map = folium.Map(location=center, zoom_start=12, control_scale=True, tiles="OpenStreetMap")
    center_label = "선택 지역의 검색 기준점" if verified else "지도 기준점 (시·도 좌표)"
    folium.Marker(
        center, tooltip=center_label, icon=folium.Icon(color="green", icon="home"),
        popup=folium.Popup(f"<b>{center_label}</b><br>{_map_safe_text(location_text(region))}", max_width=300),
    ).add_to(village_map)
    points = []
    if isinstance(places, pd.DataFrame):
        for row in places.to_dict("records"):
            point = _map_coordinates(row.get("lat"), row.get("lon"))
            if point is None:
                continue
            category = str(row.get("main_category", "장소"))
            color = {"맛집": "red", "카페": "blue", "관광지": "green", "숙박": "orange",
                     "학교": "purple", "공원": "green", "문화": "darkred", "체험": "cadetblue"}.get(category, "gray")
            popup = (f"<b>{_map_safe_text(row.get('name', '장소'))}</b><br>"
                     f"{_map_safe_text(category)}<br>{_map_safe_text(row.get('address', ''))}")
            folium.CircleMarker(
                point, radius=6, color=color, fill=True, fill_opacity=0.8,
                tooltip=_map_safe_text(row.get("name", "장소")), popup=folium.Popup(popup, max_width=300),
            ).add_to(village_map)
            points.append(point)
    if points:
        village_map.fit_bounds(
            [[min(point[0] for point in points), min(point[1] for point in points)],
             [max(point[0] for point in points), max(point[1] for point in points)]],
            padding=(24, 24), max_zoom=15,
        )
    return village_map



# ============================================================
# 17. 데이터 합치기
# ============================================================




# ============================================================
# 콘텐츠 화면
# ============================================================





# ============================================================
# 19. 콘텐츠 탐색
# ============================================================

def render_explore(region, api_key):
    st.title("지역 콘텐츠 탐색")
    st.caption("카카오 Local API에서 받은 실제 장소를 검색 조건과 API의 순서대로 보여 줍니다.")
    _trip_notice()
    st.button(f"🛒 담은 장소 {len(st.session_state.get('cart_items', []))}곳 보기", key="explore_cart",
              on_click=_trip_go, args=("장바구니",), use_container_width=True)
    categories = ["맛집", "카페", "관광지", "숙박", "학교", "공원", "문화", "체험"]
    if st.session_state.get("explore_category") not in categories:
        st.session_state["explore_category"] = categories[0]
        st.session_state.pop("explore_search_result", None)
    category = st.radio("콘텐츠", categories, horizontal=True, key="explore_category")
    location = location_text(region)
    point = _map_coordinates(region.get("lat"), region.get("lon")) if region.get("coordinates_verified") else None
    st.caption(f"선택 지역: {location}")
    if point:
        st.caption("선택한 전체 지역명 + 검색어로, 확인된 지역 기준점 반경 20km 안을 검색해요. 행정구역 경계로 잘라 낸 목록은 아니며 인접 지역이 포함될 수 있어요.")
    else:
        st.caption("지역 기준점의 좌표를 확인하지 못해 전체 지역명 + 검색어로 검색해요. 거리순은 좌표 확인 후 사용할 수 있어요.")
    sort_options = {"검색 정확도순": "accuracy"}
    if point:
        sort_options["지역 기준점에서 가까운 순"] = "distance"
    # 기준점 확인 여부가 바뀌었을 때 이전 선택을 유효한 항목으로 되돌립니다.
    _ensure_region_option("explore_sort", list(sort_options))
    with st.form("explore_search_form", enter_to_submit=True):
        query = st.text_input("검색어", value=category,
                              key=f"explore_query_{category}", placeholder="예: 학교, 맛집, 막국수, 카페")
        sort_label = st.selectbox("결과 순서", list(sort_options), key="explore_sort")
        submitted = st.form_submit_button("🔎 검색", type="primary", use_container_width=True)
    st.caption("위에서 고른 종류 안에서 검색해요. 다른 종류의 장소를 찾으려면 콘텐츠 버튼을 바꿔 주세요.")
    with st.expander("검색 결과 순서는 어떻게 정하나요?", expanded=False):
        st.markdown(
            "**검색 정확도순**은 카카오가 검색어와 조건에 맞는 정도로 반환한 순서예요. "
            "세부 점수나 계산식은 응답에 없으며 별점순·리뷰 많은 순을 뜻하지 않아요.\n\n"
            "**지역 기준점에서 가까운 순**은 확인된 지역 좌표와 장소 사이의 거리 기준이에요. "
            "내 휴대폰 위치나 실제 도로 이동 거리 기준은 아닙니다.\n\n"
            "**카카오 Local API는 별점과 평가 수를 제공하지 않아 이 앱에서 카카오 별점순 정렬은 지원하지 않습니다.** "
            "각 장소의 ‘카카오맵에서 상세·후기 보기’로 내용을 확인할 수 있어요."
        )
    if not api_key:
        st.info("장소 검색을 사용하려면 운영자가 카카오 REST API 키를 서버 설정에 등록해야 해요. 등록 후에는 자동으로 연결됩니다.")
        return
    region_key = (region.get("region_code", ""), location, point)
    if submitted:
        typed_query = query.strip()
        if not typed_query:
            st.warning("찾을 장소나 종류를 검색어에 입력해 주세요.")
            st.session_state.pop("explore_search_result", None)
            return
        full_query = typed_query if typed_query.startswith(location + " ") else f"{location} {typed_query}".strip()
        sort = sort_options[sort_label]
        with st.spinner("검색 결과의 다음 페이지까지 확인하고 있어요..."):
            documents, error, meta = kakao_keyword_search_detailed(
                full_query, point[0] if point else None, point[1] if point else None,
                api_key, CATEGORY_CODES.get(category), sort=sort,
            )
        st.session_state["explore_search_result"] = {
            "region_key": region_key, "category": category, "query": typed_query,
            "sort_label": sort_label, "documents": documents, "error": error, "meta": meta,
        }
    saved = st.session_state.get("explore_search_result")
    if not saved or saved.get("region_key") != region_key or saved.get("category") != category:
        st.info("검색어와 순서를 고른 뒤 검색을 눌러 주세요.")
        return
    documents, error, meta = saved["documents"], saved["error"], saved["meta"]
    if error:
        message = error.get("message", "장소 검색 요청을 처리하지 못했어요.")
        if documents:
            st.warning(f"일부 페이지만 가져왔어요. {message} 아래 목록이 전부는 아닙니다.")
        else:
            st.error(message)
            st.caption("검색 실패는 장소가 0곳이라는 뜻이 아닙니다. 서버의 키·API 권한·호출 한도와 연결 상태를 확인해 주세요.")
            return
    frame = kakao_results_dataframe(documents)
    result_order = "카카오 정확도순 검색 결과" if saved["sort_label"] == "검색 정확도순" else "카카오 거리순 검색 결과"
    st.subheader(f"{len(frame):,}/45곳 · {result_order}")
    st.caption(f"검색어: {saved['query']} · 순서: {saved['sort_label']} · 성공적으로 읽은 페이지: {meta.get('pages_fetched', 0)}")
    with st.expander("검색 건수와 수집 기준 자세히 보기"):
        a, b, c = st.columns(3)
        a.metric(result_order, f"{len(frame):,}/45곳", help="같은 장소 ID를 합친 실제 수집 수 / 검색당 최대 45곳입니다.")
        total = meta.get("total_count")
        pageable = meta.get("pageable_count")
        b.metric("API 검색 일치 수", f"{total:,}건" if isinstance(total, int) else "미제공")
        c.metric("API에서 표시 가능한 수", f"{pageable:,}건" if isinstance(pageable, int) else "미제공")
        st.caption("한 페이지 15건을 다음 페이지까지 읽어 검색당 최대 45건을 받습니다. 같은 장소 ID는 한 번만 표시하며, 이 숫자는 지역 전체 업소 수가 아닙니다. API 검색 일치 수가 커도 API가 공개하는 목록에는 상한이 있어요.")
    if meta.get("truncated"):
        st.warning("API의 표시 범위 또는 이 검색의 수집 상한 때문에 더 이상 목록을 가져오지 못했어요.")
    elif meta.get("partial") and not error:
        st.warning("검색 페이지 정보를 끝까지 확인하지 못했어요. 아래는 받은 결과만으로 만든 일부 목록입니다.")
    if meta.get("counts_changed"):
        st.caption("페이지를 가져오는 사이 API 검색 일치 수가 바뀌었어요. 표시한 일치 수는 마지막 응답 기준입니다.")
    if frame.empty:
        if meta.get("partial"):
            st.info("이번에 받은 응답에서 표시할 장소를 확인하지 못했어요. 검색이 불완전하므로 잠시 후 다시 검색해 주세요.")
        else:
            st.info("이 검색 조건에 일치하는 장소가 없어요. 검색어를 짧게 바꾸거나 다른 콘텐츠 종류를 선택해 보세요.")
        return
    frame["main_category"] = category
    digest = hashlib.sha256(json.dumps([region_key, saved["query"], saved["sort_label"], category], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    records = frame.to_dict("records")
    pages = list(range(1, math.ceil(len(records) / 9) + 1))
    if len(pages) > 1:
        page = st.selectbox("검색 결과 페이지 · 한 번에 9곳", pages, key=f"explore_page_{digest}",
                            format_func=lambda number: f"{number} / {len(pages)} 페이지")
    else:
        page = 1
    offset = (page - 1) * 9
    st.caption(f"전체 {len(records)}곳 중 {offset + 1}~{min(offset + 9, len(records))}번째 장소 · {result_order}")
    cart_ids = {place["identity"] for place in st.session_state.get("cart_items", [])}
    for index, row in enumerate(records[offset:offset + 9], offset + 1):
        place = _cart_normalize_place(row, region)
        with st.container(border=True):
            st.markdown(f"**{index}. {_explore_markdown(row.get('name', '장소'))}**")
            st.caption(str(row.get("category", category)))
            for field, label in (("address", "주소"), ("phone", "전화")):
                value = row.get(field)
                if value and str(value).lower() not in {"nan", "none"}:
                    st.text(f"{label}: {value}")
            safe_url = _explore_safe_url(row.get("url", ""))
            a, b = st.columns(2)
            with a:
                if place:
                    added = place["identity"] in cart_ids
                    st.button("✓ 장바구니에 담았어요" if added else "🛒 장바구니에 담기",
                              key=f"explore_add_{_trip_token(place['identity'])}",
                              type="secondary" if added else "primary", disabled=added,
                              on_click=_trip_cart_add, args=(row, region), use_container_width=True)
            with b:
                if safe_url:
                    st.link_button("카카오맵 · 상세·후기", safe_url, use_container_width=True)
    with st.expander(f"검색된 {len(records)}곳 지도에서 보기"):
        st_folium(make_map(region, frame), key=f"explore_map_{digest}", height=380,
                   use_container_width=True, returned_objects=[])
        invalid_count = sum(_map_coordinates(row.get("lat"), row.get("lon")) is None for row in records)
        if invalid_count:
            st.caption(f"좌표를 확인할 수 없는 {invalid_count}곳은 목록에만 표시했어요.")



# ============================================================
# 20. 지역 소비 시뮬레이터
# ============================================================




# ============================================================
# 21. AI 추천
# ============================================================

# ============================================================
# AI 추천: 실제 검색 장소 + 선택 관심사에 따른 규칙 기반 시간표
# ============================================================

_AI_INTEREST_OPTIONS = ["자연", "미식", "역사", "휴식", "가족", "축제"]
_AI_INTEREST_CATEGORIES = {
    "자연": ["공원", "관광지"],
    "미식": ["맛집", "카페"],
    "역사": ["문화", "관광지"],
    "휴식": ["공원", "카페"],
    "가족": ["체험", "공원", "관광지"],
    "축제": ["문화", "체험"],
}


def _ai_normalize_interests(values):
    """화면의 '맛집'과 기존 내부 값 '미식'을 같은 관심사로 취급합니다."""
    if values is None:
        values = ["자연", "미식"]
    elif isinstance(values, str):
        values = [values]
    normalized = []
    for value in values:
        value = "미식" if value == "맛집" else value
        if value in _AI_INTEREST_OPTIONS and value not in normalized:
            normalized.append(value)
    return normalized


def _ai_interest_label(value):
    return "맛집" if value == "미식" else value


def _ai_store_interests():
    # 메뉴에서 나가며 위젯 상태가 정리되어도 선택은 별도 세션 키에 남깁니다.
    st.session_state["travel_interests"] = _ai_normalize_interests(
        st.session_state.get("ai_travel_interests", [])
    )


def _ai_collect_places(local_data):
    """같은 카카오 장소가 여러 검색 분류에 나와도 한 곳으로 합칩니다."""
    by_identity = {}
    allowed = {"맛집", "카페", "관광지", "공원", "문화", "체험", "숙박"}
    for category, data in (local_data or {}).items():
        if category not in allowed:
            continue
        if isinstance(data, pd.DataFrame):
            records = data.to_dict("records")
        elif isinstance(data, (list, tuple)):
            records = data
        else:
            continue
        for row in records:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name or name.lower() in {"nan", "none", "이름 없음"}:
                continue
            address = str(row.get("address") or "").strip()
            if address.lower() in {"nan", "none"}:
                address = ""
            url = _ai_route_safe_url(row.get("url", ""))
            point = _ai_route_coordinates(row.get("lat"), row.get("lon"))
            identity = url if url else f"{name}|{address}"
            if identity in by_identity:
                if category not in by_identity[identity]["categories"]:
                    by_identity[identity]["categories"].append(category)
                # 같은 장소가 다른 검색 분류에서는 유효한 좌표를 가진 경우만 보완합니다.
                if point and by_identity[identity]["lat"] is None:
                    by_identity[identity]["lat"], by_identity[identity]["lon"] = point
                continue
            by_identity[identity] = {
                "identity": identity, "name": name, "address": address, "url": url,
                "categories": [category], "lat": point[0] if point else None,
                "lon": point[1] if point else None,
            }
    return list(by_identity.values())



def _ai_build_itinerary(local_data, interests, days):
    """순수 함수: 실제 장소·관심사·기간만으로 예시 시간표를 만듭니다."""
    selected = _ai_normalize_interests(interests)
    result = {"status": "ready", "interests": selected, "itinerary": [], "selected_places": [],
              "missing_slots": 0, "uncovered_by_day": {}, "warnings": [], "lodging": None, "lodging_nights": 0}
    if not selected:
        return {**result, "status": "choose_interest", "message": "여행 관심사를 하나 이상 선택해 주세요."}
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 3:
        return {**result, "status": "invalid", "message": "여행 기간은 1~3일 중에서 선택해 주세요."}
    places = _ai_collect_places(local_data)
    allowed = {category for interest in selected for category in _AI_INTEREST_CATEGORIES[interest]}
    if not any(allowed.intersection(place["categories"]) for place in places):
        return {**result, "status": "no_matches", "message": "선택한 관심사에 맞는 실제 장소 검색 결과가 없어요. 다른 관심사나 지역을 선택해 주세요."}
    used = set()
    day_orders = {}

    def pick(categories):
        for category in categories:
            for place in places:
                if place["identity"] not in used and category in place["categories"]:
                    used.add(place["identity"])
                    result["selected_places"].append(place)
                    return place, category
        return None, ""

    # 숙소를 먼저 한 곳 확보해 두면 관광·식사 후보와 겹치더라도 다른 일정에 중복 배치하지 않습니다.
    lodging, _ = pick(["숙박"]) if days > 1 else (None, "")
    result["lodging"] = lodging
    result["lodging_nights"] = days - 1

    def add(day, at, kind, place=None, category="", interest="", note=""):
        if place is None:
            result["missing_slots"] += 1
        matched_interests = [value for value in selected if category in _AI_INTEREST_CATEGORIES[value]] if place else []
        covered_today.update(matched_interests)
        day_orders[day] = day_orders.get(day, 0) + 1
        result["itinerary"].append({
            "일차": day, "순서": day_orders[day], "예시 시각": at, "일정": kind,
            "장소": place["name"] if place else "직접 선택",
            "분류": category, "반영한 관심사": " · ".join(_ai_interest_label(value) for value in matched_interests),
            "주소": place["address"] if place else "",
            "카카오맵": place["url"] if place else "", "안내": note,
            "_place_id": place["identity"] if place else "",
        })

    def interest_stop(day, at, phase):
        def available_categories(value):
            return [category for category in _AI_INTEREST_CATEGORIES[value]
                    if any(category in place["categories"] and place["identity"] not in used for place in places)]

        # 후보가 없는 관심사에 계속 막히지 않게 실제 남은 장소가 있는 관심사를 먼저 고릅니다.
        uncovered = [value for value in selected if value not in covered_today]
        available_uncovered = [value for value in uncovered if available_categories(value)]
        offset = ((day - 1) * 3 + phase) % len(selected)
        rotated = selected[offset:] + selected[:offset]
        available_remaining = [value for value in rotated if available_categories(value)]
        focus = (available_uncovered or available_remaining or uncovered or rotated)[0]
        categories = list(_AI_INTEREST_CATEGORIES[focus])
        if focus == "미식":
            # 오전/오후는 카페부터, 늦은 오후는 맛집부터 고릅니다.
            categories = ["카페", "맛집"] if phase < 2 else ["맛집", "카페"]
        elif phase % 2 and len(categories) > 1:
            categories = categories[1:] + categories[:1]
        # 공원은 자연·휴식·가족, 문화는 역사·축제 등 여러 선택을 함께 반영할 수 있습니다.
        # 실제 후보가 있는 범주 안에서 아직 반영하지 못한 관심사를 많이 포함하는 순서로 고릅니다.
        preferences = {category: index for index, category in enumerate(categories)}
        categories = [category for category in categories if category in available_categories(focus)]
        categories.sort(key=lambda category: (
            -sum(category in _AI_INTEREST_CATEGORIES[value] for value in uncovered),
            preferences[category],
        ))
        place, category = pick(categories)
        if place:
            note = "선택한 관심사에 맞춰 검색 결과에서 골랐어요. 영업시간·이용료는 방문 전 확인해 주세요."
            if focus == "축제":
                note = "문화·체험 장소 추천이에요. 실제 축제 개최 여부나 날짜를 확인한 것은 아닙니다."
            add(day, at, f"{_ai_interest_label(focus)} 탐방", place, category, focus, note)
        else:
            add(day, at, f"{_ai_interest_label(focus)} 탐방 / 자유 시간", interest=focus,
                note="이 관심사에서 중복 없이 추천할 장소가 더 없어 직접 정하는 시간으로 남겼어요.")

    for day in range(1, days + 1):
        covered_today = set()
        if day > 1:
            final_morning = day == days
            morning_label = "숙소 출발 · 체크아웃" if final_morning else "숙소 출발"
            if lodging:
                morning_note = (
                    "여행 내내 이용한 같은 숙소에서 출발해요. 09:00은 예시이며 실제 체크아웃 시각은 숙소에 확인해 주세요."
                    if final_morning else "전날 묵은 같은 숙소에서 출발해요. 저녁에도 이 숙소로 돌아옵니다. 출발 시각은 예시예요."
                )
            else:
                morning_note = "추천할 숙소 검색 결과가 없어 출발 위치는 직접 정해야 해요. 예약한 숙소의 위치와 체크아웃 시각을 확인해 주세요."
            add(day, "09:00", morning_label, lodging, "숙박" if lodging else "", note=morning_note)
        interest_stop(day, "10:00", 0)
        lunch, category = pick(["맛집"])
        add(day, "12:30", "점심 식사", lunch, category, "미식" if "미식" in selected else "",
            "메뉴·가격·영업시간은 카카오맵에서 확인해 주세요." if lunch else "식당 검색 결과가 부족해 직접 선택하는 식사 시간이에요.")
        interest_stop(day, "14:30", 1)
        interest_stop(day, "16:30", 2)
        dinner, category = pick(["맛집"])
        add(day, "18:30", "저녁 식사", dinner, category, "미식" if "미식" in selected else "",
            "메뉴·가격·영업시간은 카카오맵에서 확인해 주세요." if dinner else "식당 검색 결과가 부족해 직접 선택하는 식사 시간이에요.")
        if day < days:
            add(day, "20:00", "숙박", lodging, "숙박" if lodging else "", "",
                f"여행 동안 같은 숙소에서 {days - 1}박하는 일정이에요. 연박 요금·체크인 시각·예약 가능 여부는 직접 확인해 주세요."
                if lodging else "추천할 숙소 검색 결과가 없어 숙소를 직접 정해야 해요. 여행 내내 같은 숙소를 이용하도록 예약해 주세요.")
        uncovered = [value for value in selected if value not in covered_today]
        result["uncovered_by_day"][day] = uncovered
        if uncovered:
            labels = " · ".join(_ai_interest_label(value) for value in uncovered)
            result["warnings"].append(f"{day}일차에는 {labels} 관심사를 담을 중복 없는 장소를 배치하지 못했어요. 검색된 장소와 직접 선택하는 시간으로 구성했으니 필요하면 지역을 바꿔 보세요.")
    if days > 1 and lodging is None:
        result["warnings"].append("숙소 검색 결과가 없어 공통 숙소를 추천하지 못했어요. 숙박과 다음 날 출발 위치는 직접 정해야 합니다.")
    if result["missing_slots"]:
        result["warnings"].append("검색 결과가 부족한 시간은 ‘직접 선택’으로 남겼어요. 숙소를 제외한 관광·식사 장소를 반복해 채우거나 없는 장소를 만들어 넣지 않았어요.")
    if "축제" in selected:
        result["warnings"].append("축제 관심사는 문화·체험 장소 선택에 반영돼요. 축제 일정이나 개최 여부를 조회하는 기능은 아니에요.")
    return result










# ============================================================
# 예산 여행 코스: 실제 장소와 사용자가 조정한 비용 가정으로 계산
# ============================================================

_BUDGET_INTERESTS = {
    "자연": ["공원", "관광지"],
    "미식": [],
    "역사": ["문화", "관광지"],
    "휴식": ["공원", "관광지"],
    "가족": ["체험", "공원", "관광지"],
    "축제": ["문화", "체험"],
}
_BUDGET_SIGHTS = {"관광지", "공원", "문화", "체험"}


def _budget_haversine(a, b):
    """직선거리(km). 도로 경로나 실시간 길찾기 결과가 아니다."""
    lat1, lon1, lat2, lon2 = map(math.radians, [*a, *b])
    q = math.sin((lat2 - lat1) / 2) ** 2
    q += math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, q))))


def _budget_point(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    except (TypeError, ValueError):
        pass
    return None


def _budget_places(local_data, region):
    """학교·중복·좌표 없는 검색 결과를 제외한다. 이름을 만들어 넣지 않는다."""
    places, seen = [], set()
    center = _budget_point(region.get("lat"), region.get("lon"))
    allowed = _BUDGET_SIGHTS | {"맛집", "카페", "숙박"}
    for category, frame in (local_data or {}).items():
        if category not in allowed or frame is None or frame.empty:
            continue
        for row in frame.to_dict("records"):
            point = _budget_point(row.get("lat"), row.get("lon"))
            name = str(row.get("name", "")).strip()
            address = str(row.get("address", "") or "").strip()
            if not point or not name or name.lower() in {"nan", "none", "이름 없음"}:
                continue
            if center and region.get("coordinates_verified") and _budget_haversine(center, point) > 30:
                continue
            url = str(row.get("url", "") or "").strip()
            if not url.startswith(("https://place.map.kakao.com/", "http://place.map.kakao.com/")):
                url = ""
            identity = url or f"{name}|{address}"
            if identity in seen:
                continue
            seen.add(identity)
            places.append({"name": name, "address": address, "lat": point[0], "lon": point[1],
                           "url": url, "main_category": category, "identity": identity})
    return places


def _budget_island_route(origin, region):
    """확실한 도서 지명은 육로 거리 추정에서 제외한다. 모든 섬을 판별하지는 못한다."""
    destination = " ".join(str(region.get(k, "")) for k in ("sido", "sigungu", "eup"))
    if ("제주" in origin) != ("제주" in destination):
        return True
    island_names = ("울릉", "우도", "추자", "백령", "대청", "소청", "연평", "덕적", "자월", "흑산", "홍도", "가거", "청산면", "노화읍", "보길면", "소안면", "금일읍", "생일면", "욕지면", "사량면", "한산면", "남면 연도")
    return any(name in origin or name in destination for name in island_names)


def _budget_geocode_origin(origin, api_key):
    """주소 우선, 역명/장소명은 기존 카카오 키워드 검색으로 보완한다."""
    if not api_key or not origin.strip():
        return None
    result = kakao_address_search(origin.strip(), api_key)
    if result and _budget_point(result.get("lat"), result.get("lon")):
        return {"lat": result["lat"], "lon": result["lon"], "label": origin.strip()}
    documents, _ = kakao_keyword_search(origin.strip(), None, None, api_key)
    for document in documents[:1]:
        point = _budget_point(document.get("y"), document.get("x"))
        if point:
            address = document.get("road_address_name") or document.get("address_name") or ""
            return {"lat": point[0], "lon": point[1],
                    "label": f"{document.get('place_name', origin)} · {address}"}
    return None


def _budget_estimate_transport(settings, distance_km=None):
    """반환: ok, roundtrip_cost(일행 전체), one_way_minutes, local_cost, note."""
    s = settings
    people, days = int(s["people"]), int(s["days"])
    local_cost = int(s["local_daily"]) * days * (people if s["mode"] == "대중교통" else 1)
    if s["transport_input"] == "왕복 교통비 직접 입력":
        return {"ok": True, "roundtrip_cost": int(s["manual_cost"]),
                "one_way_minutes": int(s["manual_minutes"]), "local_cost": local_cost,
                "note": "직접 입력한 일행 전체 왕복비와 편도 소요시간. 현지 이동비는 별도입니다."}
    if distance_km is None or not math.isfinite(distance_km) or distance_km < 0:
        return {"ok": False, "error": "출발지와 목적지의 좌표가 필요합니다. 왕복 교통비 직접 입력을 선택할 수도 있어요."}
    route_km = distance_km * float(s["road_factor"])
    one_way_minutes = int(math.ceil(route_km / float(s["speed"]) * 60 + int(s["boarding_minutes"])))
    if s["mode"] == "자가용":
        fare = int(math.ceil(route_km * 2 * int(s["km_cost"]))) + int(s["extra_transport"])
        note = f"직선 {distance_km:.1f}km × {s['road_factor']:.2f} = 편도 추정 {route_km:.1f}km. 차량 1대 왕복 주행비 + 통행료 가정."
    else:
        one_way_fare = max(int(s["minimum_fare"]), int(math.ceil(route_km * int(s["km_cost"]))))
        fare = one_way_fare * 2 * people
        note = f"직선 {distance_km:.1f}km × {s['road_factor']:.2f} = 편도 추정 {route_km:.1f}km. 거리당 운임 가정으로 계산한 {people}명 왕복 예상비."
    return {"ok": True, "roundtrip_cost": fare, "one_way_minutes": one_way_minutes,
            "local_cost": local_cost, "note": note, "distance_km": distance_km, "route_km": route_km}


def _budget_costs(settings, transport, visits, cafes):
    s = settings
    people, days, nights = int(s["people"]), int(s["days"]), int(s["days"]) - 1
    rooms = math.ceil(people / int(s["room_people"])) if nights else 0
    rows = [
        {"항목": "출발지 ↔ 여행지 왕복 교통", "금액(원)": int(transport["roundtrip_cost"]), "기준": "일행 전체 / 왕복"},
        {"항목": "여행지 내 이동", "금액(원)": int(transport["local_cost"]), "기준": f"{days}일 현지 이동 예상비"},
        {"항목": "식비", "금액(원)": int(s["meal_cost"]) * int(s["meals"]) * people * days,
         "기준": f"1인 1끼 {s['meal_cost']:,}원 × {s['meals']}끼 × {people}명 × {days}일"},
        {"항목": "숙박비", "금액(원)": int(s["lodging"]) * rooms * nights,
         "기준": "당일치기: 숙박비 없음" if not nights else f"1실 1박 {s['lodging']:,}원 × {rooms}실 × {nights}박"},
        {"항목": "입장·체험 예상비", "금액(원)": int(s["activity"]) * people * visits,
         "기준": f"1인 1곳 {s['activity']:,}원 × {people}명 × {visits}곳 (실제 가격 확인 필요)"},
        {"항목": "카페 예상비", "금액(원)": int(s["cafe"]) * people * cafes,
         "기준": f"1인 1회 {s['cafe']:,}원 × {people}명 × {cafes}회"},
    ]
    subtotal = sum(row["금액(원)"] for row in rows)
    reserve = int(math.ceil(subtotal * int(s["reserve_pct"]) / 100))
    rows.append({"항목": "예비비", "금액(원)": reserve, "기준": f"위 예상 지출 합계의 {s['reserve_pct']}%"})
    return rows, subtotal + reserve


def _budget_clock(minutes):
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


def _budget_schedule(settings, places, transport, visit_counts, cafe_counts):
    """일별 가용시간 안에서 최근접 장소를 선택한다. 실패 시 부분 코스를 반환하지 않는다."""
    s = settings
    used, itinerary, chosen = set(), [], []
    priority = []
    for interest in s.get("interests", []):
        for category in _BUDGET_INTERESTS.get(interest, []):
            if category not in priority:
                priority.append(category)
    priority += [category for category in ("관광지", "공원", "문화", "체험") if category not in priority]
    center = tuple(s["center"])
    local_speed = 28 if s["mode"] == "자가용" else 16
    day_return = int(transport["one_way_minutes"])
    lodging_choices = [p for p in places if p["main_category"] == "숙박"]
    lodging = min(lodging_choices, key=lambda p: _budget_haversine(center, (p["lat"], p["lon"]))) if lodging_choices else None
    overnight_point = (lodging["lat"], lodging["lon"]) if lodging else center

    def append(day, start, end, kind, name, note="", place=None):
        itinerary.append({"일차": day, "시작": _budget_clock(start), "종료": _budget_clock(end),
                          "구분": kind, "일정/장소": name, "주소": place["address"] if place else "",
                          "카카오맵": place["url"] if place else "", "안내": note})

    for day in range(1, s["days"] + 1):
        now = int(s["start_minutes"])
        cutoff = int(s["end_minutes"]) - (day_return if day == s["days"] else 0)
        position = center if day == 1 else overnight_point

        def wait_until(target):
            nonlocal now
            if now < target:
                append(day, now, target, "휴식", "자유 시간 / 휴식", "개별 지출은 예비비에서 확인")
                now = target

        def move_to(point, name):
            nonlocal now, position
            direct = _budget_haversine(position, point)
            if direct < 0.05:
                position = point
                return
            if s["mode"] == "대중교통" and direct <= 0.8:
                duration = max(5, math.ceil(direct * 1.3 / 4 * 60))
                detail = "가까운 구간 도보 추정"
            else:
                duration = max(10, math.ceil(direct * 1.3 / local_speed * 60))
                if s["mode"] == "대중교통":
                    duration += 10
                detail = "직선거리 × 1.3 / 평균속도. 실제 노선·운행 여부 확인 필요"
            append(day, now, now + duration, "현지 이동", name, detail)
            now += duration
            position = point

        def choose(categories):
            candidates = [p for p in places if p["main_category"] in categories and p["identity"] not in used]
            if not candidates:
                return None
            def score(place):
                distance = _budget_haversine(position, (place["lat"], place["lon"]))
                rank = priority.index(place["main_category"]) if place["main_category"] in priority else 0
                return distance + rank * 1.5
            return min(candidates, key=score)

        def stop(place, duration, kind, fallback, note=""):
            nonlocal now
            if place:
                move_to((place["lat"], place["lon"]), f"{place['name']} 이동")
                used.add(place["identity"])
                chosen.append(place)
            append(day, now, now + duration, kind, place["name"] if place else fallback, note, place)
            now += duration

        if s["meals"] == 3:
            stop(None, 40, "아침", "아침 식사 · 직접 선택", "식비에 포함")
        if day == 1:
            append(day, now, now + day_return, "가는 교통", f"{s['origin']} → 선택 여행지", "예상 소요시간 / 왕복 교통비에 포함")
            now += day_return
        if now > 14 * 60:
            return {"ok": False, "error": "목적지 도착이 오후 2시 이후라 첫날 점심과 방문 일정을 넣기 어렵습니다. 출발을 앞당기거나 가까운 지역을 선택해 주세요."}

        # 점심 전 시간이 충분하면 첫 명소를 방문하고, 늦게 도착하면 식사를 먼저 한다.
        before_lunch = bool(visit_counts[day - 1] and now + 100 <= 13 * 60)
        if before_lunch:
            sight = choose(_BUDGET_SIGHTS)
            if not sight:
                return {"ok": False, "error": "중복 없이 배치할 실제 방문 장소가 부족합니다."}
            stop(sight, 75, "방문", "", "영업일·운영시간·입장료는 방문 전 확인")
        wait_until(11 * 60 + 30)
        if now > 14 * 60:
            return {"ok": False, "error": "현지 이동시간 때문에 점심 일정이 너무 늦어집니다. 가까운 지역이나 다른 교통수단을 선택해 주세요."}
        stop(choose({"맛집"}), 50, "점심", "점심 식사 · 식당 직접 선택", "입력한 1인 1끼 예상비 사용 / 메뉴 가격 미확인")
        for _ in range(visit_counts[day - 1] - int(before_lunch)):
            sight = choose(_BUDGET_SIGHTS)
            if not sight:
                return {"ok": False, "error": "중복 없이 배치할 실제 방문 장소가 부족합니다."}
            stop(sight, 75, "방문", "", "영업일·운영시간·입장료는 방문 전 확인")
        if cafe_counts[day - 1]:
            cafe = choose({"카페"})
            if not cafe:
                return {"ok": False, "error": "중복 없는 카페 검색 결과가 부족합니다."}
            stop(cafe, 40, "카페", "", "입력한 음료 예상비 사용 / 메뉴 가격 미확인")
        append(day, now, now + 20, "휴식", "휴식 / 일정 여유", "추가 지출은 예비비에서 확인")
        now += 20
        if s["meals"] >= 2:
            wait_until(17 * 60)
            stop(choose({"맛집"}), 50, "저녁", "저녁 식사 · 식당 직접 선택", "입력한 1인 1끼 예상비 사용 / 메뉴 가격 미확인")
        if day == s["days"]:
            move_to(center, "여행지 출발 지점으로 이동")
            if now > cutoff:
                return {"ok": False, "error": "왕복 이동·식사·최소 방문시간을 더하면 귀가 마감시간을 넘습니다. 더 가까운 지역, 빠른 출발, 늦은 귀가 또는 숙박 여행을 선택해 주세요."}
            append(day, now, now + day_return, "오는 교통", f"선택 여행지 → {s['origin']}", "귀가 / 왕복 교통비에 포함")
            now += day_return
        else:
            move_to(overnight_point, "숙소 방향으로 이동")
            append(day, now, now + 30, "숙박", lodging["name"] if lodging else "숙소 · 직접 예약", "입력한 객실 예상비 기준 / 요금·예약 가능 여부 미확인", lodging)
            now += 30
            if lodging and lodging["identity"] not in {p["identity"] for p in chosen}:
                chosen.append(lodging)
        if now > int(s["end_minutes"]):
            return {"ok": False, "error": "하루 이동·식사·방문시간이 설정한 하루 마감시간을 넘습니다. 시작/마감시간이나 여행지를 조정해 주세요."}
    return {"ok": True, "itinerary": itinerary, "selected_places": chosen}


def _budget_make_plan(settings, places, transport):
    """순수 계산 진입점. over_budget/time_infeasible 상태에는 실행 가능한 코스를 내지 않는다."""
    s = settings
    base = {"ok": False, "status": "invalid", "itinerary": [], "selected_places": [], "warnings": [],
            "breakdown": [], "total": 0, "remaining": int(s.get("budget", 0)), "minimum_required": 0, "shortfall": 0}
    if not str(s.get("origin", "")).strip():
        return {**base, "error": "출발지 주소나 역명을 입력해 주세요. 왕복 교통비 직접 입력도 출발지 이름이 필요합니다."}
    if int(s["budget"]) <= 0:
        return {**base, "error": "일행 전체 여행 예산을 0원보다 크게 입력해 주세요."}
    if not 1 <= int(s["days"]) <= 3 or int(s["people"]) < 1:
        return {**base, "error": "여행 일수는 1~3일, 여행 인원은 1명 이상이어야 합니다."}
    if s["mode"] == "자가용" and int(s["people"]) > 5 and s["transport_input"] != "왕복 교통비 직접 입력":
        return {**base, "error": "6명 이상은 차량 수에 따른 전체 왕복비를 직접 입력해 주세요."}
    if int(s["end_minutes"]) <= int(s["start_minutes"]):
        return {**base, "error": "하루 마감시간은 시작시간보다 늦게 설정해 주세요."}
    if not transport.get("ok"):
        return {**base, "error": transport.get("error", "교통비를 계산할 수 없습니다.")}
    if int(transport["one_way_minutes"]) <= 0:
        return {**base, "error": "편도 이동시간은 1분 이상 입력해 주세요. 대기·환승 시간도 포함해 주세요."}
    days = int(s["days"])
    sights_available = sum(p["main_category"] in _BUDGET_SIGHTS for p in places)
    cafes_available = sum(p["main_category"] == "카페" for p in places)
    minimum_visits = min(days, sights_available) if sights_available else days
    minimum_rows, minimum_total = _budget_costs(s, transport, minimum_visits, 0)
    base.update({"breakdown": minimum_rows, "total": minimum_total, "remaining": s["budget"] - minimum_total,
                 "minimum_required": minimum_total, "shortfall": max(0, minimum_total - s["budget"])})
    if minimum_total > s["budget"]:
        return {**base, "status": "over_budget", "error": f"설정한 교통·식사·숙박·최소 방문·예비비 기준으로 {minimum_total - s['budget']:,}원이 부족합니다. 실제 비용을 확인해 가정을 바꾸거나 예산·여행지를 조정해 주세요."}
    min_daily_minutes = int(s["meals"]) * 50 + 75 + 20
    available_minutes = (int(s["end_minutes"]) - int(s["start_minutes"])) * days
    if int(transport["one_way_minutes"]) * 2 + min_daily_minutes * days > available_minutes:
        return {**base, "status": "time_infeasible", "error": "설정한 왕복 이동시간과 최소 식사·방문시간만으로 하루 가용시간을 초과합니다. 가까운 여행지를 고르거나 여행 일수를 늘려 주세요."}
    if not sights_available:
        return {**base, "ok": True, "status": "budget_only", "warnings": ["실제 관광·공원·문화·체험 장소가 없어 예산 계산만 제공합니다. 하루 1곳 방문비를 임시 배정했으며, 실제 여행 코스는 생성하지 않았습니다."]}
    # 최소 방문을 하루씩 배치하고 여유 예산으로 방문지와 카페를 늘린다.
    base_counts = [1 if d < min(days, sights_available) else 0 for d in range(days)]
    variants = []
    max_extra = min(days, max(0, sights_available - sum(base_counts)))
    wants_cafe = any(x in s.get("interests", []) for x in ("미식", "휴식"))
    max_cafes = min(days, cafes_available) if wants_cafe else 0
    for extras in range(max_extra, -1, -1):
        for cafe_total in range(max_cafes, -1, -1):
            visits = [count + int(d < extras) for d, count in enumerate(base_counts)]
            cafes = [int(d < cafe_total) for d in range(days)]
            rows, total = _budget_costs(s, transport, sum(visits), sum(cafes))
            if total <= s["budget"]:
                variants.append((sum(visits) + sum(cafes), visits, cafes, rows, total))
    # 미식·휴식 관심이면 같은 방문 수에서 카페가 포함된 조합을 먼저 고른다.
    variants.sort(key=lambda v: (v[0], sum(v[2]) if wants_cafe else 0), reverse=True)
    last_error = "이동시간과 방문시간이 맞는 코스를 만들지 못했습니다. 지역이나 시간 설정을 조정해 주세요."
    for _, visits, cafes, rows, total in variants:
        schedule = _budget_schedule(s, places, transport, visits, cafes)
        if not schedule["ok"]:
            last_error = schedule["error"]
            continue
        warnings = ["모든 금액은 입력한 가정에 따른 예상치입니다. 카카오 검색에는 실제 교통 운임·메뉴 가격·입장료·객실 요금·예약 가능 여부가 포함되지 않습니다.",
                    "표의 시간은 실제 노선표나 운영시간이 아닙니다. 방문 전 카카오맵에서 이동 경로와 장소 영업시간을 확인해 주세요."]
        if sights_available < days:
            warnings.append("검색된 방문 장소가 여행 일수보다 적어 일부 날은 식사·휴식 위주입니다. 장소를 반복해 채우지 않았습니다.")
        if s["activity"] == 0:
            warnings.append("입장·체험비를 0원으로 설정했습니다. 방문지가 무료라고 확인된 것은 아니므로 각 장소의 비용을 확인해 주세요.")
        if sum(visits) < days * 2 or sum(cafes) < max_cafes:
            warnings.append("예산과 하루 가용시간에 맞춰 방문지·카페 수를 조정했습니다.")
        return {**base, **schedule, "ok": True, "status": "ready", "breakdown": rows, "total": total,
                "remaining": s["budget"] - total, "shortfall": 0, "warnings": warnings,
                "visit_count": sum(visits), "cafe_count": sum(cafes)}
    return {**base, "status": "time_infeasible", "error": last_error}


def _budget_fingerprint(settings, region, places, api_key=""):
    payload = {"settings": settings, "region": {k: str(region.get(k, "")) for k in ("sido", "sigungu", "eup", "region_code", "coordinates_verified")},
               "places": places, "api_key_digest": hashlib.sha256(api_key.encode("utf-8")).hexdigest()}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _budget_csv(rows):
    # 외부 장소명이 스프레드시트 수식으로 해석되지 않도록 방어한다.
    def safe_cell(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value
    return pd.DataFrame([{key: safe_cell(value) for key, value in row.items()} for row in rows]).to_csv(index=False).encode("utf-8-sig")


def _render_budget_builder_legacy(region, local_data, interests, days, api_key):
    st.title("예산에 맞는 여행 코스")
    st.caption("선택한 지역의 실제 장소를 연결하고 왕복 교통·현지 이동·식사·숙박·예비비를 함께 계산해요.")
    st.caption("자연·역사 등은 방문지 종류에, 미식·휴식은 카페 배치에 반영해요. 식당은 코스 주변의 실제 검색 결과에서 골라요.")
    duration = "당일치기" if days == 1 else f"{days - 1}박 {days}일"
    st.info(f"여행지: {location_text(region)} · {duration} · 여행 기간은 왼쪽에서, 관심사는 AI 추천 화면에서 변경할 수 있어요.")
    c1, c2 = st.columns([2, 1])
    with c1:
        budget = st.number_input("여행 예산 · 일행 전체 총액 (원)", min_value=0, value=150000, step=10000, key="trip_budget")
    with c2:
        people = st.number_input("여행 인원 (명)", min_value=1, max_value=20, value=1, step=1, key="trip_people")
    origin = st.text_input("출발지 주소 또는 역명", placeholder="예: 서울역, 경기도 수원시 영통구 ...", key="trip_origin")
    c1, c2 = st.columns(2)
    with c1:
        mode = st.selectbox("교통수단", ["대중교통", "자가용"], key="trip_mode")
    with c2:
        transport_input = st.selectbox("왕복 교통비 계산 방법", ["거리로 대략 계산", "왕복 교통비 직접 입력"], key="trip_transport_input")
    c1, c2 = st.columns(2)
    with c1:
        start_time = st.time_input("하루 시작 시각", value=trip_clock_time(8, 0), step=900, key="trip_start")
    with c2:
        end_time = st.time_input("귀가 / 숙소 도착 마감", value=trip_clock_time(21, 0), step=900, key="trip_end")
    route_type = st.selectbox("이동 경로 종류", ["육로 이동", "항공·배편 포함"], key="trip_route_type")
    air_ferry = route_type == "항공·배편 포함"
    manual_cost, manual_minutes = 0, 60
    if transport_input == "왕복 교통비 직접 입력":
        c1, c2 = st.columns(2)
        with c1:
            manual_cost = st.number_input("출발지 ↔ 여행지 왕복비 · 일행 전체 (원)", min_value=0, value=40000, step=1000, key="trip_manual_cost")
        with c2:
            manual_minutes = st.number_input("편도 이동시간 · 대기/환승 포함 (분)", min_value=1, max_value=1440, value=90, step=10, key="trip_manual_minutes")
        st.caption("왕복비는 모든 인원·차량의 합계예요. 항공·배편과 여러 차량의 요금도 합쳐 입력하고, 여행지 안에서 쓰는 이동비는 아래에 따로 입력해 주세요.")
    else:
        st.caption("육로 이동을 기준으로 직선거리에 도로 우회계수를 곱한 거친 예상입니다. 실제 길찾기·열차/버스 요금·배차 정보가 아닙니다. 섬·항공·배편은 왕복비와 편도시간을 직접 입력해 주세요.")

    with st.expander("식비·숙박비·교통비 가정 조정", expanded=False):
        st.caption("아래 기본값은 계산용 예시 금액입니다. 확인한 실제 가격이나 본인의 소비 계획에 맞춰 변경해 주세요.")
        c1, c2, c3 = st.columns(3)
        with c1:
            meal_cost = st.number_input("식비 · 1인 1끼 (원)", min_value=0, value=12000, step=1000, key="trip_meal_cost")
            meals = st.selectbox("식사 횟수 · 1인 하루", [1, 2, 3], index=1, key="trip_meals",
                                 help="1끼: 점심 / 2끼: 점심·저녁 / 3끼: 아침·점심·저녁")
        with c2:
            activity = st.number_input("입장·체험비 · 1인 1곳 (원)", min_value=0, value=10000, step=1000, key="trip_activity")
            cafe = st.number_input("카페 · 1인 1회 (원)", min_value=0, value=6000, step=1000, key="trip_cafe")
        with c3:
            local_daily = st.number_input("현지 이동비 · 1인 하루 (원)" if mode == "대중교통" else "현지 주행·주차비 · 차량 전체 하루 (원)",
                                          min_value=0, value=8000 if mode == "대중교통" else 15000, step=1000,
                                          key="trip_local_transit" if mode == "대중교통" else "trip_local_car")
            reserve_pct = st.number_input("예비비 · 예상 지출의 (%)", min_value=0, max_value=50, value=10, step=1, key="trip_reserve")
        lodging, room_people = 0, 2
        if days > 1:
            c1, c2 = st.columns(2)
            with c1:
                lodging = st.number_input("숙박비 · 객실 1개 1박 (원)", min_value=0, value=80000, step=10000, key="trip_lodging")
            with c2:
                room_people = st.number_input("객실 1개당 인원 (명)", min_value=1, max_value=20, value=2, step=1, key="trip_room_people")
        else:
            st.caption("당일치기는 숙박비를 0원으로 계산해요.")
        road_factor, km_cost, minimum_fare, extra_transport, speed, boarding_minutes = 1.3, 150, 5000, 10000, 60, 30
        if transport_input == "거리로 대략 계산":
            c1, c2, c3 = st.columns(3)
            with c1:
                road_factor = st.number_input("도로 우회계수 · 직선거리 배수", min_value=1.0, max_value=3.0, value=1.3, step=0.1, key="trip_road_factor")
                speed = st.number_input("장거리 평균 이동속도 가정 (km/h)", min_value=10, max_value=200, value=60, step=5, key="trip_speed")
            with c2:
                km_cost = st.number_input("1인 편도 1km당 운임 가정 (원)" if mode == "대중교통" else "차량 1km당 주행비 가정 (원)",
                                          min_value=0, value=150 if mode == "대중교통" else 200, step=10,
                                          key="trip_km_transit" if mode == "대중교통" else "trip_km_car")
                boarding_minutes = st.number_input("편도 추가 여유 · 대기/환승 (분)", min_value=0, max_value=240, value=30, step=5, key="trip_boarding")
            with c3:
                if mode == "대중교통":
                    minimum_fare = st.number_input("1인 편도 최소운임 가정 (원)", min_value=0, value=5000, step=1000, key="trip_minimum_fare")
                else:
                    extra_transport = st.number_input("왕복 통행료 · 차량 1대 합계 (원)", min_value=0, value=10000, step=1000, key="trip_toll")
            st.caption("자동 계산은 자가용 1대 기준입니다. 6명 이상 또는 여러 차량은 왕복비를 직접 입력해 주세요. 현지 이동시간도 거리 추정이므로 실제 교통편을 반드시 확인해 주세요.")

    places = _budget_places(local_data, region)
    center = _budget_point(region.get("lat"), region.get("lon")) or (36.5, 127.8)
    if not region.get("coordinates_verified") and places:
        first_place = next((p for p in places if p["main_category"] in _BUDGET_SIGHTS), places[0])
        center = (first_place["lat"], first_place["lon"])
    settings = {"budget": int(budget), "people": int(people), "origin": origin.strip(), "days": int(days),
                "mode": mode, "transport_input": transport_input, "manual_cost": int(manual_cost), "manual_minutes": int(manual_minutes),
                "start_minutes": start_time.hour * 60 + start_time.minute, "end_minutes": end_time.hour * 60 + end_time.minute,
                "air_ferry": air_ferry, "meal_cost": int(meal_cost), "meals": int(meals),
                "activity": int(activity), "cafe": int(cafe), "local_daily": int(local_daily), "reserve_pct": int(reserve_pct),
                "lodging": int(lodging), "room_people": int(room_people), "road_factor": float(road_factor), "km_cost": int(km_cost),
                "minimum_fare": int(minimum_fare), "extra_transport": int(extra_transport), "speed": int(speed),
                "boarding_minutes": int(boarding_minutes), "center": center, "interests": list(interests)}
    fingerprint = _budget_fingerprint(settings, region, places, api_key)
    if st.session_state.get("trip_result_fingerprint") not in (None, fingerprint):
        st.session_state.pop("trip_result", None)
        st.session_state.pop("trip_result_fingerprint", None)
        st.info("지역이나 조건이 바뀌어 이전 코스를 지웠어요. 새 조건으로 다시 만들어 주세요.")

    if st.button("예산에 맞춰 코스 만들기", type="primary", key="trip_generate", use_container_width=True):
        error, origin_result, transport = None, None, None
        if not origin.strip():
            error = "출발지 주소나 역명을 입력해 주세요."
        elif budget <= 0:
            error = "일행 전체 예산을 0원보다 크게 입력해 주세요."
        elif transport_input == "거리로 대략 계산":
            if air_ferry or _budget_island_route(origin, region):
                error = "항공·배편 또는 도서 지역은 육로 거리로 계산할 수 없어요. 왕복 교통비 직접 입력을 선택해 실제 예상 왕복비와 편도시간을 넣어 주세요."
            elif not api_key:
                error = "거리 계산은 운영자의 카카오 서버 설정 후 사용할 수 있어요. 지금은 왕복 교통비 직접 입력을 이용해 주세요."
            elif not region.get("coordinates_verified") and not places:
                error = "선택 지역의 정확한 좌표를 확인하지 못했어요. 왕복 교통비와 편도시간을 직접 입력해 주세요."
            else:
                with st.spinner("출발지와 왕복 이동 거리를 확인하고 있어요..."):
                    origin_result = _budget_geocode_origin(origin, api_key)
                if not origin_result:
                    error = "출발지를 찾지 못했어요. 시·군·구를 포함한 주소나 정확한 역명을 입력하거나 왕복 교통비를 직접 입력해 주세요."
                else:
                    distance = _budget_haversine((origin_result["lat"], origin_result["lon"]), center)
                    transport = _budget_estimate_transport(settings, distance)
        else:
            transport = _budget_estimate_transport(settings)
        if error:
            st.session_state.pop("trip_result", None)
            st.error(error)
        else:
            result = _budget_make_plan(settings, places, transport)
            result["transport"] = transport
            result["origin_resolved"] = origin_result["label"] if origin_result else origin.strip()
            if not region.get("coordinates_verified") and places:
                result["warnings"].append("행정구역 좌표 대신 실제 검색 장소의 좌표를 도착 기준점으로 사용했습니다.")
            st.session_state["trip_result"] = result
            st.session_state["trip_result_fingerprint"] = fingerprint

    result = st.session_state.get("trip_result")
    if not result or st.session_state.get("trip_result_fingerprint") != fingerprint:
        return
    st.divider()
    if result.get("error"):
        st.error(result["error"])
    elif result["status"] == "ready":
        st.success("입력한 예상비 기준으로 예산과 하루 가용시간 안에 들어오는 코스를 만들었어요.")
    elif result["status"] == "budget_only":
        st.warning("예산 계산 완료 · 실제 장소가 없어 여행 코스는 아직 만들지 않았어요.")
    for warning in result.get("warnings", []):
        st.caption(warning)
    if not result["breakdown"]:
        return
    a, b, c = st.columns(3)
    a.metric("전체 예산", f"{budget:,}원")
    b.metric("예상 총액 · 일행 전체", f"{result['total']:,}원")
    c.metric("부족한 금액" if result["remaining"] < 0 else "남는 예산", f"{abs(result['remaining']):,}원")
    st.caption(f"{people}명 · {duration} · 1인 평균 예상 {math.ceil(result['total'] / people):,}원. 이미 포함된 예비비와 남는 예산은 별도입니다.")
    st.dataframe(pd.DataFrame(result["breakdown"]), use_container_width=True, hide_index=True)
    if result.get("transport"):
        st.caption(f"출발지 확인: {result['origin_resolved']}")
        st.caption(result["transport"]["note"])
        st.caption(f"편도 이동 예상 {result['transport']['one_way_minutes']}분 · 현지 이동비 {result['transport']['local_cost']:,}원 별도 반영")
    if result["status"] == "over_budget":
        st.info(f"현재 입력 조건의 최소 코스 예상액은 {result['minimum_required']:,}원이에요. 예산을 초과하는 코스를 적정 예산인 것처럼 제시하지 않습니다.")
    if result["status"] != "ready":
        st.download_button("예산 계산표 CSV 다운로드", _budget_csv(result["breakdown"]), file_name="villageon_budget.csv", mime="text/csv", key="trip_budget_download")
        return
    st.subheader("시간순 여행 코스")
    st.caption("출발·귀가와 식사·휴식·현지 이동을 포함한 예상 일정입니다. 식당이 부족한 끼니는 ‘직접 선택’으로 표시합니다.")
    itinerary_df = pd.DataFrame(result["itinerary"])
    for day in range(1, days + 1):
        st.markdown(f"### {day}일차")
        day_df = itinerary_df[itinerary_df["일차"] == day].drop(columns=["일차"])
        st.dataframe(day_df, use_container_width=True, hide_index=True,
                     column_config={"카카오맵": st.column_config.LinkColumn("카카오맵", display_text="장소 확인")})
    map_places = pd.DataFrame(result["selected_places"])
    if not map_places.empty:
        st.subheader("코스에 포함된 실제 장소")
        st.caption("지도는 장소 위치를 표시합니다. 실제 이동 경로를 그린 길찾기 지도가 아닙니다.")
        trip_map_region = {**region, "lat": center[0], "lon": center[1]}
        st_folium(make_map(trip_map_region, map_places), height=430, use_container_width=True, returned_objects=[], key=f"trip_map_{fingerprint[:12]}")
    export_rows = []
    for row in result["itinerary"]:
        export_rows.append({"여행지": location_text(region), "인원": people, "여행일수": days, "전체예산(원)": budget,
                            "전체예상액(원)": result["total"], "남는예산(원)": result["remaining"], **row})
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("여행 코스 CSV 다운로드", _budget_csv(export_rows), file_name="villageon_itinerary.csv", mime="text/csv", key="trip_itinerary_download", use_container_width=True)
    with c2:
        st.download_button("예산 계산표 CSV 다운로드", _budget_csv(result["breakdown"]), file_name="villageon_budget.csv", mime="text/csv", key="trip_budget_download", use_container_width=True)


# ============================================================
# 화면 스타일: 배경과 입력 글자 색을 각각 지정합니다.
# ============================================================

def load_css():
    st.markdown(
        """
<style>
.stApp,
[data-testid="stAppViewContainer"] {
    background: #f7faf8;
    color: #172a3a;
    color-scheme: light;
}
[data-testid="stHeader"] { background: rgba(247, 250, 248, 0.96); }
[data-testid="stSidebar"] { background: #123c3a; color: #f7fbf8; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label p,
[data-testid="stSidebar"] [data-testid="stCheckbox"] label p {
    color: #f7fbf8 !important;
}
[data-testid="stSidebar"] hr { border-color: #4d7470; }
[data-testid="stSidebar"] [data-testid="stAlert"] {
    background: #e9f3ee;
    color: #172a3a;
}
[data-testid="stSidebar"] [data-testid="stAlert"] p { color: #172a3a !important; }

/* 키 입력, 검색어, 숫자, 시간, 선택 상자에 동일한 읽기 쉬운 색을 사용합니다. */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-testid="stTimeInput"] input,
[data-testid="stDateInput"] input,
[data-testid="stSelectbox"] input,
[data-testid="stMultiSelect"] input,
[data-testid="stSelectbox"] [role="combobox"],
[data-testid="stMultiSelect"] [role="combobox"] {
    color: #172a3a !important;
    -webkit-text-fill-color: #172a3a !important;
    background-color: #ffffff !important;
    caret-color: #172a3a !important;
    opacity: 1 !important;
}
[data-testid="stTextInputRootElement"],
[data-testid="stNumberInputContainer"],
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stTimeInput"] [data-baseweb="select"] > div,
[data-testid="stDateInput"] [data-baseweb="input"],
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    color: #172a3a !important;
    background-color: #ffffff !important;
    border-color: #b9cdc4 !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] span,
[data-testid="stSelectbox"] [data-baseweb="select"] div,
[data-testid="stMultiSelect"] [data-baseweb="select"] span {
    color: #172a3a !important;
    -webkit-text-fill-color: #172a3a !important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] {
    background: #dfefe6 !important;
    color: #123c3a !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder,
[data-testid="stSelectbox"] input::placeholder,
[data-testid="stMultiSelect"] input::placeholder {
    color: #667c73 !important;
    -webkit-text-fill-color: #667c73 !important;
    opacity: 1 !important;
}
[data-testid="stTextInput"] button,
[data-testid="stNumberInput"] button,
[data-testid="stSelectbox"] button,
[data-testid="stMultiSelect"] button,
[data-testid="stTimeInput"] button {
    color: #244d40 !important;
    background-color: #ffffff !important;
}
[data-testid="stTextInput"] svg,
[data-testid="stSelectbox"] svg,
[data-testid="stMultiSelect"] svg {
    color: #244d40 !important;
    fill: currentColor;
}

/* 선택 목록은 사이드바 바깥에 생성될 수도 있어 별도로 지정합니다. */
[role="listbox"],
[data-baseweb="popover"] ul,
[data-baseweb="menu"] {
    background-color: #ffffff !important;
    color: #172a3a !important;
}
[role="option"],
[role="option"] span,
[role="option"] div,
[role="option"] p,
[data-baseweb="menu"] li {
    color: #172a3a !important;
    -webkit-text-fill-color: #172a3a !important;
    background-color: #ffffff !important;
}
[role="option"][aria-selected="true"],
[role="option"][data-focused="true"],
[role="option"]:hover {
    background-color: #e0f0e7 !important;
}
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {
    background: #ffffff;
    color: #123c3a;
    border: 1px solid #b9cdc4;
    border-radius: 8px;
}
[data-testid="stButton"] button[kind="primary"],
[data-testid="stDownloadButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button {
    background: #1f6b52;
    border-color: #1f6b52;
    color: #ffffff;
}
[data-testid="stButton"] button p,
[data-testid="stDownloadButton"] button p,
[data-testid="stFormSubmitButton"] button p { color: inherit !important; }
/* 휴대폰에서 키보드 Enter 대신 보이는 버튼을 편하게 누를 수 있게 합니다. */
[data-testid="stFormSubmitButton"] button {
    min-height: 44px;
    width: 100%;
    -webkit-text-fill-color: #ffffff !important;
}
[data-testid="stFormSubmitButton"] button p {
    -webkit-text-fill-color: #ffffff !important;
}
[data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMain"] [data-testid="stMetricValue"],
[data-testid="stMain"] [data-testid="stMetricLabel"] p {
    color: #172a3a;
}
.hero {
    background: #123c3a;
    color: #f7fbf8;
    padding: 42px;
    border-radius: 10px;
    margin-bottom: 24px;
}
.hero h1 { color: #ffffff !important; }
.hero p { color: #dcefe6 !important; }
.eyebrow {
    color: #bde7d5 !important;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
}
div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #d9e4df;
    padding: 12px;
    border-radius: 8px;
}

/* 메뉴와 콘텐츠 선택은 라디오의 실제 클릭 라벨을 큰 카드로 표시합니다.
   Streamlit 1.66의 stRadioOption / data-selected / data-focus-visible을 사용합니다. */
[data-testid="stRadioGroup"] {
    gap: 10px !important;
    padding: 2px 0;
}
[data-testid="stRadioGroup"][data-orientation="vertical"] {
    align-items: stretch !important;
}
[data-testid="stRadioGroup"][data-orientation="vertical"] > div {
    width: 100%;
    min-width: 0;
}
[data-testid="stRadioGroup"][data-orientation="horizontal"] {
    align-items: stretch !important;
    flex-wrap: wrap !important;
}
[data-testid="stRadioGroup"][data-orientation="horizontal"] > div {
    flex: 0 1 auto;
    min-width: 0;
    max-width: 100%;
}
[data-testid="stRadio"] [data-testid="stRadioOption"] {
    display: flex !important;
    align-items: center;
    box-sizing: border-box;
    min-height: 56px;
    height: 100%;
    max-width: 100%;
    margin: 0 !important;
    padding: 12px 16px !important;
    border: 2px solid #b9cdc4;
    border-radius: 12px;
    background: #ffffff;
    color: #172a3a;
    font-size: 17px;
    line-height: 1.45;
    transition: background-color 120ms ease, border-color 120ms ease;
    -webkit-tap-highlight-color: transparent;
}
[data-testid="stRadio"] [data-testid="stRadioOption"] > div {
    min-width: 0;
    width: 100%;
}
[data-testid="stRadio"] [data-testid="stRadioOption"] p {
    color: #172a3a !important;
    -webkit-text-fill-color: #172a3a !important;
    font-size: 17px !important;
    font-weight: 600;
    line-height: 1.45 !important;
    white-space: normal !important;
    overflow-wrap: anywhere;
    word-break: keep-all;
}
[data-testid="stRadio"] [data-testid="stRadioOption"]:not([data-disabled]):hover {
    border-color: #24795d;
    background: #eef7f1;
}
[data-testid="stRadio"] [data-testid="stRadioOption"][data-selected] {
    border-color: #1f6b52;
    background: #dff1e7;
    box-shadow: inset 0 0 0 1px #1f6b52;
}
[data-testid="stRadio"] [data-testid="stRadioOption"][data-focus-visible] {
    outline: 3px solid #24795d;
    outline-offset: 3px;
}
[data-testid="stRadio"] [data-testid="stRadioOption"][data-disabled] {
    cursor: not-allowed;
    opacity: 0.6;
}

/* 어두운 사이드바에서는 미선택·선택 상태의 대비를 각각 확보합니다. */
[data-testid="stSidebar"] [data-testid="stRadioOption"] {
    width: 100%;
    background: #1c514d;
    border-color: #658c85;
}
[data-testid="stSidebar"] [data-testid="stRadioOption"] p {
    color: #f7fbf8 !important;
    -webkit-text-fill-color: #f7fbf8 !important;
    font-size: 18px !important;
}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:not([data-disabled]):hover {
    background: #28655e;
    border-color: #b4dfc9;
}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected] {
    background: #e1f3e8;
    border-color: #a8ddbe;
    box-shadow: inset 0 0 0 1px #a8ddbe;
}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected] p {
    color: #123c3a !important;
    -webkit-text-fill-color: #123c3a !important;
}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-focus-visible] {
    outline-color: #d7f7e3;
}

/* 실행·검색·다운로드·링크 버튼만 키워 입력 칸의 작은 보조 버튼은 유지합니다. */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button,
[data-testid="stLinkButton"] a {
    box-sizing: border-box;
    min-height: 56px;
    height: auto;
    max-width: 100%;
    min-width: 0;
    padding: 12px 18px;
    border: 2px solid #b9cdc4;
    border-radius: 12px;
    background: #ffffff;
    color: #123c3a;
    -webkit-text-fill-color: #123c3a !important;
    font-size: 17px;
    font-weight: 600;
    line-height: 1.45;
    white-space: normal;
    overflow-wrap: anywhere;
    text-decoration: none;
    touch-action: manipulation;
}
[data-testid="stButton"] button [data-testid="stMarkdownContainer"],
[data-testid="stDownloadButton"] button [data-testid="stMarkdownContainer"],
[data-testid="stFormSubmitButton"] button [data-testid="stMarkdownContainer"],
[data-testid="stLinkButton"] a [data-testid="stMarkdownContainer"] {
    min-width: 0;
    max-width: 100%;
    white-space: normal !important;
    overflow: visible;
    text-overflow: clip;
}
[data-testid="stButton"] button p,
[data-testid="stDownloadButton"] button p,
[data-testid="stFormSubmitButton"] button p,
[data-testid="stLinkButton"] a p {
    color: inherit !important;
    -webkit-text-fill-color: inherit !important;
    font-size: 17px !important;
    font-weight: 600;
    line-height: 1.45 !important;
    white-space: normal !important;
    overflow-wrap: anywhere;
    word-break: keep-all;
}
[data-testid="stButton"] button[kind="primary"],
[data-testid="stDownloadButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button,
[data-testid="stLinkButton"] a[kind="primary"] {
    background: #1f6b52;
    border-color: #1f6b52;
    color: #ffffff;
    -webkit-text-fill-color: #ffffff !important;
}
[data-testid="stButton"] button:not(:disabled):hover,
[data-testid="stDownloadButton"] button:not(:disabled):hover,
[data-testid="stFormSubmitButton"] button:not(:disabled):hover,
[data-testid="stLinkButton"] a:not([aria-disabled="true"]):hover {
    border-color: #123c3a;
}
[data-testid="stButton"] button:focus-visible,
[data-testid="stDownloadButton"] button:focus-visible,
[data-testid="stFormSubmitButton"] button:focus-visible,
[data-testid="stLinkButton"] a:focus-visible {
    outline: 3px solid #328464;
    outline-offset: 3px;
}
[data-testid="stSidebar"] [data-testid="stButton"] button:focus-visible,
[data-testid="stSidebar"] [data-testid="stLinkButton"] a:focus-visible {
    outline-color: #d7f7e3;
}
@media (max-width: 640px) {
    [data-testid="stRadioGroup"][data-orientation="horizontal"] > div {
        flex: 1 1 auto;
    }
    [data-testid="stRadio"] [data-testid="stRadioOption"] {
        padding: 12px 14px !important;
    }
}
@media (prefers-reduced-motion: reduce) {
    [data-testid="stRadio"] [data-testid="stRadioOption"] {
        transition: none;
    }
}

</style>
""",
        unsafe_allow_html=True,
    )



def _region_selection_changed(level):
    """상위 지역을 바꾸면 하위 선택을 새 목록에 맞춰 초기화합니다."""
    st.session_state.pop("region_notice", None)
    if level == "sido":
        st.session_state.pop("region_sigungu", None)
        st.session_state.pop("region_eup", None)
    elif level == "sigungu":
        st.session_state.pop("region_eup", None)


def _recommend_region_callback(regions):
    current = (
        st.session_state.get("region_sido", ""),
        st.session_state.get("region_sigungu", ""),
        st.session_state.get("region_eup", ""),
    )
    selected = choose_random_region(regions, current)
    if selected is None:
        return
    # 버튼 콜백은 다음 화면의 위젯 생성 전에 실행됩니다.
    st.session_state["region_sido"] = selected["sido"]
    st.session_state["region_sigungu"] = selected["sigungu"]
    st.session_state["region_eup"] = selected["eupmyeondong"]
    st.session_state["view"] = "예산 여행 코스"
    st.session_state["budget_mode"] = "예산으로 새 코스 찾기"
    st.session_state["budget_mode_saved"] = "예산으로 새 코스 찾기"
    st.session_state["region_notice"] = " ".join(
        selected[k] for k in ("sido", "sigungu", "eupmyeondong") if selected[k]
    )


def _ensure_region_option(key, options):
    if options and st.session_state.get(key) not in options:
        st.session_state[key] = options[0]


def _kakao_connection_state(local_data):
    """기존 검색 응답의 상태만 요약합니다. 확인용 API 요청을 추가하지 않습니다."""
    successes, failures, places = 0, 0, 0
    for frame in (local_data or {}).values():
        if not isinstance(frame, pd.DataFrame):
            continue
        places += len(frame)
        if "api_request_count" in frame.attrs:
            successes += int(frame.attrs.get("api_success_count", 0))
            failures += int(frame.attrs.get("api_error_count", 0))
        else:
            # 이전 캐시에 결과가 있으면 정상 응답의 근거가 있지만 빈 표만으로는 알 수 없습니다.
            successes += int(not frame.empty)
            failures += int(bool(frame.attrs.get("api_error")))
    if failures and not successes:
        return {
            "status": "failure", "level": "error",
            "message": "카카오 연결 실패 · 모든 장소 검색 요청이 실패했어요. REST API 키·Local API 권한·사용 한도와 인터넷 연결을 확인해 주세요.",
        }
    if failures and successes:
        return {
            "status": "partial_failure", "level": "warning",
            "message": "카카오 일부 검색 실패 · 정상 응답을 받은 검색도 있어요. 표시되는 장소 목록이 일부일 수 있으니 키·권한·사용 한도를 확인해 주세요."
            if places else "카카오 일부 검색 실패 · 정상 응답을 받은 검색에서는 장소를 찾지 못했어요. 키·권한·사용 한도를 확인하거나 다른 지역을 선택해 주세요.",
        }
    if successes:
        return {
            "status": "success" if places else "empty", "level": "success",
            "message": "카카오 연결 성공 · 실제 장소 검색 결과를 받았어요."
            if places else "카카오 연결 성공 · 검색 요청은 정상 처리됐지만 이 지역의 장소 결과가 없어요.",
        }
    return {
        "status": "unverified", "level": "info",
        "message": "카카오 연결 확인 대기 · 정상 검색 응답을 아직 확인하지 못했어요.",
    }


# ============================================================
# 앱 실행
# ============================================================

def main():
    _trip_init_state()
    load_css()
    _trip_extra_css()
    admin_api_key = load_secret_safely("ADMIN_API_KEY")
    kakao_api_key = load_secret_safely("KAKAO_REST_API_KEY")
    # 이전 버전의 입력값은 정리합니다. 서버 키를 위젯이나 세션으로 복사하지 않습니다.
    for old_key in ("admin_api_key_input", "user_admin_api_key", "kakao_api_key_input", "user_kakao_api_key", "api_keys_submit"):
        st.session_state.pop(old_key, None)

    with st.sidebar:
        st.title("🌱 VillageON")
        st.caption("장소를 담고, 시간표와 예산을 한 번에.")
        st.divider()
        with st.expander("데이터 연결 상태", expanded=False):
            st.subheader("데이터 연결")
            st.caption("설정한 API 키로 자동 연결해요. 방문자는 키를 입력할 필요가 없어요.")
            admin_connection_status = st.empty()
            kakao_connection_status = st.empty()
            if admin_api_key:
                admin_connection_status.info("행정안전부 설정을 읽었어요. 전국 지역 목록으로 연결 상태를 확인해요.")
            else:
                admin_connection_status.info("행정안전부 연결 준비 중 · 운영자 설정이 필요해요.")
            if kakao_api_key:
                kakao_connection_status.info("카카오 설정을 읽었어요. 장소 검색으로 연결 상태를 확인해요.")
            else:
                kakao_connection_status.info("카카오 연결 준비 중 · 운영자 설정이 필요해요.")
            st.divider()

    if not admin_api_key:
        st.title("전국 어디로 떠나 볼까요?")
        st.info("전국 지역 목록을 위한 서버 연결이 아직 준비되지 않았어요. 운영자가 API 키를 한 번 등록하면 이 화면에서 자동으로 지역 선택을 시작할 수 있어요.")
        _render_operator_setup()
        st.stop()

    try:
        with st.spinner("전국 법정동 목록을 모두 불러오는 중이에요. 처음에는 잠시 걸릴 수 있어요..."):
            admin_df = load_admin_regions(admin_api_key)
            regions = build_region_dataframe(admin_df)
    except AdminRegionLoadError as exc:
        admin_connection_status.error("행정안전부 연결 실패 · 전국 지역 목록을 끝까지 불러오지 못했어요. 키·활용신청 승인·인터넷 연결을 확인해 주세요.")
        st.error(str(exc))
        st.info("서비스 활용신청 승인, 일반 인증키(Decoding), 인터넷 연결을 확인한 뒤 다시 시도해 주세요.")
        if st.button("지역 목록 다시 불러오기", key="retry_regions"):
            load_admin_regions.clear()
            st.rerun()
        st.stop()
    if regions.empty:
        admin_connection_status.error("행정안전부 연결 실패 · 선택 가능한 전국 지역 목록을 받지 못했어요. 서비스키와 API 활용 승인을 확인해 주세요.")
        st.error("시·도와 읍·면·동까지 연결된 지역 목록을 받지 못했어요. 서비스키와 API 활용 승인을 확인해 주세요.")
        if st.button("지역 목록 다시 불러오기", key="retry_regions"):
            load_admin_regions.clear()
            st.rerun()
        st.stop()

    admin_connection_status.success("행정안전부 연결 성공 · 전국 지역 목록을 확인했어요.")

    with st.sidebar:
        menu_options = list(_TRIP_MENU)
        if st.session_state.get("view") == "대시보드":
            st.session_state["view"] = "지역 소비 시뮬레이터"
        _ensure_region_option("view", menu_options)
        view = st.radio("메뉴", menu_options, key="view")
        st.divider()
        st.subheader("전국 지역 선택")
        st.button(
            "🎲 지역 추천", key="recommend_region", use_container_width=True,
            on_click=_recommend_region_callback, args=(regions,),
            help="실제 행정구역 조합을 무작위로 고르고 예산 여행 코스로 이동해요.",
        )
        st.caption("시·도 → 시·군·구 → 읍·면·동을 한 번에 추천해요.")
        sido_options = sorted(regions["sido"].dropna().unique().tolist())
        _ensure_region_option("region_sido", sido_options)
        sido = st.selectbox(
            "시·도", sido_options, key="region_sido",
            on_change=_region_selection_changed, args=("sido",),
        )
        sigungu_options = sorted(regions.loc[regions["sido"] == sido, "sigungu"].unique().tolist())
        _ensure_region_option("region_sigungu", sigungu_options)
        sigungu = st.selectbox(
            "시·군·구", sigungu_options, key="region_sigungu",
            format_func=lambda value: value or "해당 없음 (세종특별자치시)",
            disabled=sigungu_options == [""],
            on_change=_region_selection_changed, args=("sigungu",),
        )
        eup_options = sorted(regions.loc[
            (regions["sido"] == sido) & (regions["sigungu"] == sigungu), "eupmyeondong"
        ].unique().tolist())
        _ensure_region_option("region_eup", eup_options)
        eup = st.selectbox(
            "읍·면·동", eup_options, key="region_eup",
            on_change=_region_selection_changed, args=("eup",),
        )
        st.caption("행정안전부 법정동 기준이에요. 일부 명칭은 주민센터의 행정동과 다를 수 있어요.")
        if st.session_state.get("region_notice"):
            st.success("추천 여행지: " + st.session_state["region_notice"])
        st.divider()
        duration_options = {"당일치기": 1, "1박 2일": 2, "2박 3일": 3}
        duration = st.session_state.get("travel_duration", st.session_state.get("saved_travel_duration", "당일치기"))
        if duration not in duration_options:
            duration = "당일치기"
        if view in {"장바구니", "AI 추천", "예산 여행 코스"}:
            if "travel_duration" not in st.session_state:
                st.session_state["travel_duration"] = duration
            duration = st.selectbox("여행 기간", list(duration_options), key="travel_duration")
        st.session_state["saved_travel_duration"] = duration
        days = duration_options[duration]

    _trip_render_nav(view)

    # 관심사 위젯이 없는 메뉴에서도 선택을 유지합니다.
    # 위젯용 키와 별도 상태로 보관하고, 기존 '미식' 값은 예산 코스와 공유합니다.
    st.session_state["travel_interests"] = _ai_normalize_interests(
        st.session_state.get("travel_interests", ["자연", "미식"])
    )
    interests = list(st.session_state["travel_interests"])

    matches = regions[
        (regions["sido"] == sido)
        & (regions["sigungu"] == sigungu)
        & (regions["eupmyeondong"] == eup)
    ]
    if matches.empty:
        st.error("현재 선택과 연결된 지역을 찾지 못했어요. 지역 추천을 다시 눌러 주세요.")
        st.stop()
    selected = matches.iloc[0]
    if view == "지역 소비 시뮬레이터":
        # 이 화면의 계산에는 실제 장소 검색·콘텐츠 지수가 필요하지 않습니다.
        simulator_region = {"sido": sido, "sigungu": sigungu, "eup": eup, "region_code": selected["region_code"]}
        kakao_connection_status.empty()
        render_consumption_simulator(simulator_region)
        return
    simple_region = {"sido": sido, "sigungu": sigungu, "eup": eup, "region_code": selected["region_code"]}
    if view == "장바구니":
        kakao_connection_status.empty()
        render_cart(simple_region, days)
        return
    if view == "예산 여행 코스" and _trip_budget_selected_mode() == "시간표 예산 계산":
        kakao_connection_status.empty()
        render_budget_trip(simple_region, {}, interests, days, kakao_api_key)
        return
    if view == "AI 추천" and _trip_ai_source() == "장바구니 장소로":
        kakao_connection_status.empty()
        render_ai(simple_region, {}, {}, interests, days)
        return
    resolved = resolve_region_location(sido, sigungu, eup, kakao_api_key)
    region = {
        "sido": sido, "sigungu": sigungu, "eup": eup,
        "region_code": selected["region_code"],
        "lat": resolved["lat"], "lon": resolved["lon"],
        "coordinates_verified": resolved["coordinates_verified"],
        "destination_address": " ".join(x for x in (sido, sigungu, eup) if x),
    }
    if view == "콘텐츠 탐색":
        if kakao_api_key:
            kakao_connection_status.info("장소를 검색하면 연결 결과를 확인할 수 있어요.")
        render_explore(region, kakao_api_key)
        return
    local_data = {}
    if kakao_api_key:
        kakao_connection_status.info("카카오 연결 확인 중 · 선택 지역의 실제 장소를 검색해요.")
        with st.spinner("선택 지역 주변의 실제 장소를 찾고 있어요..."):
            local_data = collect_local_data(
                sido, sigungu, eup,
                region["lat"] if region["coordinates_verified"] else None,
                region["lon"] if region["coordinates_verified"] else None,
                kakao_api_key,
            )
        if not region["coordinates_verified"]:
            st.warning("선택한 읍·면·동의 좌표를 확인하지 못해 전체 지역명으로 장소를 검색했어요. 지도 중심은 시·도 기준입니다.")
        kakao_state = _kakao_connection_state(local_data)
        getattr(kakao_connection_status, kakao_state["level"])(kakao_state["message"])
        if kakao_state["status"] in {"failure", "partial_failure", "unverified"}:
            getattr(st, kakao_state["level"])(kakao_state["message"])
        elif kakao_state["status"] == "empty":
            st.info("카카오 연결은 정상이지만 이 지역의 장소 검색 결과가 없어요. 다른 읍·면·동을 선택하거나 지역 추천을 눌러 보세요.")
    else:
        kakao_connection_status.info("카카오 서버 설정 없음 · 실제 장소 검색을 준비 중이에요.")
        st.warning("운영자가 카카오 REST API 키를 서버 설정에 등록하면 실제 장소와 출발지 거리를 자동으로 검색해요. 설정 전에는 왕복 교통비를 직접 입력하는 예산 계산을 사용할 수 있어요.")
    st.caption("장소 검색은 선택 지역 주변을 포함합니다. 검색된 장소 수는 해당 지역 전체 시설 수나 공식 통계가 아닙니다.")

    if view == "AI 추천":
        render_ai(region, {}, local_data, interests, days)
    elif view == "예산 여행 코스":
        render_budget_trip(region, local_data, interests, days, kakao_api_key)



def _render_operator_setup():
    with st.expander("운영자 최초 설정 안내"):
        st.markdown(
            "**내 컴퓨터에서 코드로 설정:** `app.py` 맨 위의 두 빈 문자열에 발급받은 키를 넣고 저장한 다음 앱을 다시 실행하세요. "
            "아래는 입력할 위치를 보여 주는 예시이며, 이 화면에서 값을 입력받지는 않습니다."
        )
        st.code('ADMIN_API_KEY = "발급받은 행정안전부 Decoding 키"\nKAKAO_REST_API_KEY = "발급받은 카카오 REST API 키"', language="python")
        st.markdown(
            "**GitHub로 배포:** 코드의 두 값은 빈칸으로 두고 Streamlit 앱의 Settings → Secrets에 같은 이름으로 등록하세요. "
            "실제 키를 넣은 `app.py`는 공개 저장소에 올리지 마세요.\n\n"
            "**기존 설정 도우미:** `setup_api_keys.bat`로 저장한 설정도 계속 사용할 수 있어요. "
            "코드에 두 키가 이미 있으면 실행 도우미도 키를 다시 묻지 않습니다."
        )
        st.caption("코드 직접 설정 → Streamlit Secrets → 환경변수 → 로컬 설정 도우미 파일 순서로 읽습니다. 방문자에게는 API 키 입력창이 나타나지 않습니다.")




def _map_coordinates(lat, lon):
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    try:
        point = (float(lat), float(lon))
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(value) for value in point):
        return None
    return point if 33 <= point[0] <= 38.7 and 124 <= point[1] <= 132 else None



def _map_safe_text(value):
    return (html.escape(str(value), quote=True)
            .replace("\\", "&#92;").replace("`", "&#96;").replace("$", "&#36;"))



def _explore_safe_url(value):
    match = re.fullmatch(r"https?://place\.map\.kakao\.com/([0-9]+)/?", str(value).strip())
    return f"https://place.map.kakao.com/{match.group(1)}" if match else ""



def _explore_markdown(value):
    return re.sub(r"([\\`*_{}\[\]()#+.!|<>])", r"\\\1", str(value))




def _data_text(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()



def _data_categories():
    return ("맛집", "카페", "관광지", "숙박", "학교", "공원", "문화", "체험")



def _kakao_place_identity(item):
    """ID 우선. ID가 없을 때도 같은 이름의 다른 지점을 합치지 않습니다."""
    place_id = _data_text(item.get("place_id")) or _data_text(item.get("id"))
    url = _data_text(item.get("place_url")) or _data_text(item.get("url"))
    if not place_id and url:
        match = re.search(r"(?:place\.map\.kakao\.com/|map\.kakao\.com/link/map/)(\d+)", url)
        if match:
            place_id = match.group(1)
    if place_id:
        return ("id", place_id)
    if url:
        return ("url", url)
    name = _data_text(item.get("place_name")) or _data_text(item.get("name"))
    address = (
        _data_text(item.get("road_address_name"))
        or _data_text(item.get("address_name"))
        or _data_text(item.get("address"))
    )
    if address:
        return ("name_address", name.casefold(), address)
    latitude = _data_text(item.get("y")) or _data_text(item.get("lat"))
    longitude = _data_text(item.get("x")) or _data_text(item.get("lon"))
    return ("name_location", name.casefold(), latitude, longitude, _data_text(item.get("phone")))



def _kakao_nonnegative_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value



@st.cache_data(ttl=600, show_spinner=False)
def kakao_keyword_search_detailed(query, lat, lon, api_key, category_code=None, sort="accuracy"):
    """페이지당 15개, 최대 3페이지. 결과와 검색 범위·수집 상태를 함께 반환합니다."""
    query = _data_text(query)
    meta = {
        "query": query, "sort": sort, "total_count": None, "pageable_count": None,
        "pages_fetched": 0, "request_count": 0, "success_count": 0, "error_count": 0,
        "raw_count": 0, "unique_count": 0, "duplicates_removed": 0,
        "partial": False, "truncated": False, "limited_by_api": False,
        "status": "not_requested", "radius_m": None, "is_end": None,
        "metadata_complete": False, "stop_reason": "not_requested", "counts_changed": False,
    }
    if not api_key or not query:
        return [], None, meta
    coordinates = None
    try:
        latitude, longitude = float(lat), float(lon)
        if math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180:
            coordinates = (latitude, longitude)
    except (TypeError, ValueError, OverflowError):
        pass
    if sort not in {"accuracy", "distance"} or (sort == "distance" and coordinates is None):
        meta.update(status="error", stop_reason="invalid_sort")
        return [], {"status": -2, "message": "거리순 검색에는 확인된 지역 좌표가 필요해요. 정확도순으로 검색해 주세요."}, meta
    params_base = {"query": query, "size": 15, "sort": sort}
    if coordinates:
        params_base.update(x=coordinates[1], y=coordinates[0], radius=20000)
        meta["radius_m"] = 20000
    if category_code:
        params_base["category_group_code"] = category_code
    documents, error, seen = [], None, set()
    for page in range(1, 4):
        meta["request_count"] += 1
        try:
            response = requests.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers={"Authorization": f"KakaoAK {api_key}"},
                params={**params_base, "page": page}, timeout=10,
            )
            if response.status_code != 200:
                error = {"status": response.status_code, "message": kakao_error_message(response)}
                meta["error_count"] += 1
                meta["stop_reason"] = "request_failed"
                break
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("documents"), list):
                raise ValueError("Invalid search response")
            page_documents = body["documents"]
            if not all(isinstance(item, dict) for item in page_documents):
                raise ValueError("Invalid search records")
            # 문서 객체만 있고 장소 식별 정보가 없는 응답을 실제 장소로 세지 않습니다.
            if any(not (_data_text(item.get("id")) or _data_text(item.get("place_name"))) for item in page_documents):
                raise ValueError("Missing place identity")
        except (requests.RequestException, ValueError, TypeError):
            error = {"status": -1, "message": "카카오 장소 검색 응답을 확인하지 못했어요. 인터넷 연결과 API 설정을 확인한 뒤 다시 검색해 주세요."}
            meta["error_count"] += 1
            meta["stop_reason"] = "request_failed"
            break
        meta["pages_fetched"] += 1
        meta["success_count"] += 1
        meta["raw_count"] += len(page_documents)
        for item in page_documents:
            identity = _kakao_place_identity(item)
            if identity in seen:
                meta["duplicates_removed"] += 1
                continue
            seen.add(identity)
            documents.append(item)
        api_meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
        total_count = _kakao_nonnegative_int(api_meta.get("total_count"))
        pageable_count = _kakao_nonnegative_int(api_meta.get("pageable_count"))
        is_end = api_meta.get("is_end") if isinstance(api_meta.get("is_end"), bool) else None
        if meta["total_count"] is not None and total_count is not None and total_count != meta["total_count"]:
            meta["counts_changed"] = True
        meta.update(total_count=total_count, pageable_count=pageable_count, is_end=is_end)
        meta["metadata_complete"] = total_count is not None and pageable_count is not None and is_end is not None
        if total_count is not None and pageable_count is not None:
            meta["limited_by_api"] = total_count > pageable_count
        if is_end is True:
            meta["stop_reason"] = "last_page"
            break
        if pageable_count is not None and page * 15 >= pageable_count:
            meta["stop_reason"] = "pageable_limit"
            break
        if is_end is None and pageable_count is None:
            meta["partial"] = True
            meta["stop_reason"] = "metadata_unavailable"
            break
        if page == 3:
            meta.update(truncated=True, partial=True, stop_reason="three_page_limit")
    meta["unique_count"] = len(documents)
    if error:
        meta["partial"] = bool(documents)
        meta["status"] = "partial" if documents else "error"
    elif meta["partial"]:
        meta["status"] = "partial"
    else:
        meta["status"] = "ok" if documents else "empty"
    return documents, error, meta



def _data_deduplicate_frame(frame):
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy()
    # 위치 기준으로 처리해 원본 인덱스가 중복이어도 행이 다시 늘어나지 않습니다.
    result = frame.copy()
    identities = result.apply(_kakao_place_identity, axis=1)
    result = result.loc[~identities.duplicated()].reset_index(drop=True)
    result.attrs = dict(frame.attrs)
    return result



def _data_category_status(frame):
    if frame is None:
        return "not_requested"
    meta = frame.attrs.get("search_meta", {})
    if meta.get("status") in {"ok", "empty", "partial", "error", "not_requested"}:
        return meta["status"]
    if frame.attrs.get("api_error") or frame.attrs.get("api_error_count", 0):
        return "partial" if not frame.empty else "error"
    if not frame.empty:
        return "ok"
    return "empty" if frame.attrs.get("api_success_count", 0) else "not_requested"































def _ai_route_coordinates(lat, lon):
    """카카오 장소 좌표만 사용하며, 누락값과 국내 검색 범위 밖 좌표를 제외합니다."""
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    try:
        point = (float(lat), float(lon))
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(value) for value in point):
        return None
    # 제주·독도를 포함하는 국내 장소 검색 범위입니다. 좌표를 추측하거나 보정하지 않습니다.
    if not (33.0 <= point[0] <= 38.7 and 124.0 <= point[1] <= 132.0):
        return None
    return point



def _ai_route_safe_url(value):
    """카카오 장소 상세 URL의 숫자 ID만 받아 안전한 HTTPS 링크로 만듭니다."""
    match = re.fullmatch(r"https?://place\.map\.kakao\.com/([0-9]+)/?", str(value).strip())
    return f"https://place.map.kakao.com/{match.group(1)}" if match else ""



def _ai_route_html(value):
    # Folium 툴팁과 팝업은 HTML을 JS 템플릿 문자열에 넣으므로 두 문맥 모두 처리합니다.
    return (html.escape(str(value), quote=True)
            .replace("\\", "&#92;").replace("`", "&#96;").replace("$", "&#36;"))



def _ai_route_day_data(plan, day):
    """시간표의 장소 ID와 실제 좌표를 연결하고, 좌표가 없는 일정에서 선을 끊습니다."""
    places = {place["identity"]: place for place in plan.get("selected_places", [])
              if isinstance(place, dict) and place.get("identity")}
    route = {"day": day, "stops": [], "points": [], "segments": [], "missing": []}
    segment = []
    rows = [row for row in plan.get("itinerary", []) if row.get("일차") == day]
    for order, row in enumerate(rows, 1):
        place = places.get(row.get("_place_id", ""), {})
        point = _ai_route_coordinates(place.get("lat"), place.get("lon"))
        stop = {**row, "순서": order, "_coordinates": point}
        route["stops"].append(stop)
        if point is None:
            route["missing"].append(stop)
            if segment:
                route["segments"].append(segment)
                segment = []
        else:
            route["points"].append(stop)
            segment.append(stop)
    if segment:
        route["segments"].append(segment)
    return route



def _ai_route_map(route):
    """일정 좌표를 순서대로 잇고, 같은 좌표에 돌아오면 순번을 함께 표시합니다."""
    points = route.get("points", [])
    if not points:
        return None
    day = int(route["day"])
    color = ("#0f766e", "#2563eb", "#c2410c")[(day - 1) % 3]
    route_map = folium.Map(
        location=points[0]["_coordinates"], zoom_start=15,
        control_scale=True, tiles="OpenStreetMap",
    )
    for segment in route["segments"]:
        if len(segment) < 2:
            continue
        folium.PolyLine(
            [stop["_coordinates"] for stop in segment], color=color, weight=4, opacity=0.85,
            tooltip=f"{day}일차 방문 순서 {segment[0]['순서']} → {segment[-1]['순서']} (직선 개요)",
        ).add_to(route_map)
    grouped = {}
    for stop in points:
        grouped.setdefault(stop["_coordinates"], []).append(stop)
    for point, stops in grouped.items():
        marker_label = "·".join(str(stop["순서"]) for stop in stops)
        descriptions = []
        popup_rows = []
        for stop in stops:
            title = f"{day}일차 {stop['순서']}번 · {stop.get('예시 시각', '')} · {stop.get('장소', '')}"
            descriptions.append(f"{stop['순서']}번 {stop.get('일정', '')}")
            safe_url = _ai_route_safe_url(stop.get("카카오맵", ""))
            link = (f'<br><a href="{safe_url}" target="_blank" rel="noopener noreferrer">카카오맵에서 장소 확인</a>'
                    if safe_url else "")
            popup_rows.append(
                f"<b>{_ai_route_html(title)}</b><br>"
                f"{_ai_route_html(stop.get('일정', ''))} · {_ai_route_html(stop.get('분류', '') or '장소')}<br>"
                f"{_ai_route_html(stop.get('주소', ''))}{link}"
            )
        popup = ('<div style="font-size:14px;line-height:1.6;overflow-wrap:anywhere;">'
                 + '<hr style="margin:8px 0;">'.join(popup_rows) + '</div>')
        width = max(32, len(marker_label) * 8 + 14)
        marker_html = (
            f'<div role="img" aria-label="{day}일차 {marker_label}번" '
            f'style="min-width:{width}px;height:32px;border-radius:999px;background:{color};color:#fff;'
            'border:2px solid white;box-shadow:0 1px 5px #0006;display:flex;align-items:center;'
            f'justify-content:center;font-size:15px;font-weight:700;">{marker_label}</div>'
        )
        tooltip = f"{day}일차 · {stops[0].get('장소', '')} · " + " / ".join(descriptions)
        folium.Marker(
            point, tooltip=_ai_route_html(tooltip), popup=folium.Popup(popup, max_width=310),
            icon=folium.DivIcon(html=marker_html, icon_size=(width + 4, 36), icon_anchor=((width + 4) / 2, 18)),
        ).add_to(route_map)
    if len(grouped) > 1:
        route_map.fit_bounds(
            [[min(point[0] for point in grouped), min(point[1] for point in grouped)],
             [max(point[0] for point in grouped), max(point[1] for point in grouped)]],
            padding=(24, 24), max_zoom=15,
        )
    return route_map




def _ai_route_map_key(region, interests, days, route):
    payload = {
        "region": [str(region.get(key, "")) for key in ("sido", "sigungu", "eup")],
        "interests": _ai_normalize_interests(interests), "days": days, "day": route["day"],
        "stops": [(stop["순서"], stop.get("_place_id", ""), stop.get("예시 시각", ""),
                   stop["_coordinates"]) for stop in route["stops"]],
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return f"ai_route_day_{route['day']}_{digest[:16]}"





















_IMPACT_ITEMS = {
    "food": "식비", "cafe": "카페·간식", "activities": "입장·체험",
    "local_transport": "현지 교통", "shopping": "쇼핑·기타",
}


def _impact_round_ratio(numerator, denominator):
    """0 이상 값의 반올림. 정확히 절반이면 올립니다."""
    return (2 * int(numerator) + int(denominator)) // (2 * int(denominator))



def _impact_integer(value, label, maximum=None):
    if isinstance(value, bool):
        raise ValueError(f"{label}에는 0 이상의 정수를 입력해 주세요.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label}에는 숫자를 입력해 주세요.") from None
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError(f"{label}에는 0 이상의 정수를 입력해 주세요.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label}은 {maximum:,} 이하여야 해요.")
    return int(number)



def _impact_calculate(settings):
    """단가·비율을 실제 통계로 해석하지 않는 순수 계산 함수입니다."""
    try:
        visitors = _impact_integer(settings.get("visitors", 0), "추가 방문객", 10000000)
        overnight_pct = _impact_integer(settings.get("overnight_pct", 0), "숙박 전환율", 100)
        overnight_people = _impact_round_ratio(visitors * overnight_pct, 100)
        day_people = visitors - overnight_people
        avg_nights = float(settings.get("avg_nights", 1))
        if not math.isfinite(avg_nights) or avg_nights < 0 or avg_nights > 30:
            raise ValueError("평균 숙박일은 0~30박 사이로 입력해 주세요.")
        nights_tenths = int(round(avg_nights * 10))
        if abs(avg_nights * 10 - nights_tenths) > 0.000001:
            raise ValueError("평균 숙박일은 소수 첫째 자리까지만 입력해 주세요.")
        if overnight_people and avg_nights < 1:
            raise ValueError("숙박 여행객이 있으면 평균 숙박일을 1박 이상으로 입력해 주세요.")
        nights_units = overnight_people * nights_tenths
        days_units = overnight_people * (nights_tenths + 10)
        day_costs, overnight_costs = settings.get("day_costs", {}), settings.get("overnight_daily_costs", {})
        shares = settings.get("local_share_pct", {})
        if not all(isinstance(value, dict) for value in (day_costs, overnight_costs, shares)):
            raise ValueError("항목별 지출과 지역 내 비중 설정을 확인해 주세요.")
        rows = []
        for code, label in {**_IMPACT_ITEMS, "lodging": "숙박비"}.items():
            share = _impact_integer(shares.get(code, 0), f"{label} 지역 내 비중", 100)
            if code == "lodging":
                day_rate = 0
                overnight_rate = _impact_integer(settings.get("lodging_per_night", 0), "1인 1박 숙박비")
                day_spend = 0
                overnight_spend = _impact_round_ratio(nights_units * overnight_rate, 10)
                unit = "1인·1박"
            else:
                day_rate = _impact_integer(day_costs.get(code, 0), f"당일객 {label}")
                overnight_rate = _impact_integer(overnight_costs.get(code, 0), f"숙박객 {label}")
                day_spend = day_people * day_rate
                overnight_spend = _impact_round_ratio(days_units * overnight_rate, 10)
                unit = "1인·1일"
            total = day_spend + overnight_spend
            local = _impact_round_ratio(total * share, 100)
            rows.append({
                "항목": label, "단가 기준": unit, "당일객 단가(원)": day_rate,
                "숙박객 단가(원)": overnight_rate, "당일객 지출(원)": day_spend,
                "숙박객 지출(원)": overnight_spend, "전체 지출(원)": total,
                "지역 내 비중(%)": share, "지역 내 지출(원)": local, "지역 밖 지출(원)": total - local,
            })
        total_spend = sum(row["전체 지출(원)"] for row in rows)
        local_spend = sum(row["지역 내 지출(원)"] for row in rows)
        return {
            "ok": True, "period_label": str(settings.get("period_label", "선택 기간")).strip() or "선택 기간",
            "visitors": visitors, "overnight_pct": overnight_pct, "day_people": day_people,
            "overnight_people": overnight_people, "avg_nights": avg_nights,
            "overnight_person_nights": nights_units / 10, "overnight_person_days": days_units / 10,
            "day_person_days": day_people, "rows": rows, "total_spend": total_spend,
            "local_spend": local_spend, "outside_spend": total_spend - local_spend,
            "per_visitor_spend": _impact_round_ratio(total_spend, visitors) if visitors else 0,
            "per_visitor_local": _impact_round_ratio(local_spend, visitors) if visitors else 0,
            "weighted_local_pct": local_spend / total_spend * 100 if total_spend else 0.0,
            "actual_overnight_pct": overnight_people / visitors * 100 if visitors else 0.0,
        }
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "입력한 숫자와 항목별 설정을 확인해 주세요."
        return {"ok": False, "error": message}






def _impact_csv(rows):
    def safe(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return value
    return pd.DataFrame([{key: safe(value) for key, value in row.items()} for row in rows]).to_csv(index=False).encode("utf-8-sig")












def _ai_candidate_categories(interests):
    """선택 관심사의 검색 분야를 순서대로 모으되 같은 분야는 한 번만 둡니다."""
    categories = []
    for interest in _ai_normalize_interests(interests):
        for category in _AI_INTEREST_CATEGORIES[interest]:
            if category not in categories:
                categories.append(category)
    return categories



def _ai_candidate_result(local_data, category):
    """한 검색 분야의 응답 순서를 유지한 최대 45곳. 분야 간 순위는 만들지 않습니다."""
    original = (local_data or {}).get(category)
    if isinstance(original, pd.DataFrame):
        frame = original
    elif isinstance(original, (list, tuple)):
        frame = pd.DataFrame([row for row in original if isinstance(row, dict)])
    else:
        frame = None
    status = _data_category_status(frame)
    meta = dict(frame.attrs.get("search_meta", {})) if frame is not None else {}
    if meta.get("partial") or meta.get("truncated"):
        status = "partial"
    unique = _data_deduplicate_frame(frame)
    rows = []
    for index, row in enumerate(unique.head(45).to_dict("records"), 1):
        rows.append({
            "목록 순서": index,
            "장소명": _data_text(row.get("name")) or "이름 정보 없음",
            "분류": _data_text(row.get("category")),
            "주소": _data_text(row.get("address")),
            "카카오맵": _ai_route_safe_url(row.get("url", "")) or None,
        })
    sort = meta.get("sort")
    sort_label = {"accuracy": "카카오 정확도순 검색 결과", "distance": "카카오 거리순 검색 결과"}.get(sort, "검색 결과 순서 · 정렬 정보 미확인")
    return {
        "category": category, "rows": rows, "count": len(rows), "received_count": len(unique),
        "status": status, "sort": sort, "sort_label": sort_label,
        "partial": status == "partial", "meta": meta,
    }



def _ai_candidate_render(local_data, interests):
    categories = _ai_candidate_categories(interests)
    if not categories:
        return {"unresolved": False}
    states = {category: _ai_candidate_result(local_data, category) for category in categories}
    unresolved = any(result["status"] in {"not_requested", "error", "partial"} for result in states.values())
    st.subheader("관심사별 추천 후보 장소")
    st.caption("관심사에 연결된 분야를 골라 최대 45곳씩 볼 수 있어요. 분야마다 별도로 검색한 목록이며, 여러 분야를 합친 통합 정확도 순위는 만들지 않습니다.")
    if st.session_state.get("ai_candidate_category") not in categories:
        # 처음에는 확인된 후보가 가장 많은 관련 분야를 보여 주고, 동률이면 관심사 순서를 따릅니다.
        st.session_state["ai_candidate_category"] = max(
            categories, key=lambda value: states[value]["count"]
            if states[value]["status"] not in {"not_requested", "error"} else -1,
        )
    category = st.selectbox(
        "추천 후보 분야", categories, key="ai_candidate_category",
        format_func=lambda value: f"{value} · " + (
            "확인 불가/45곳" if states[value]["status"] in {"not_requested", "error"}
            else f"{states[value]['count']}/45곳"
        ),
    )
    result = states[category]
    unavailable = result["status"] in {"not_requested", "error"}
    count_label = "확인 불가/45곳" if unavailable else f"{result['count']}/45곳"
    st.markdown(f"**{category} {count_label} · {result['sort_label']}**")
    st.caption("후보 목록은 검색 결과의 순서이고, 아래 시간표와 지도는 방문할 순서예요. 45곳은 한 분야에서 확인하는 후보 목록의 기준이며 하루에 45곳을 방문한다는 뜻은 아닙니다.")
    if result["status"] == "not_requested":
        st.info(f"{category} 후보를 아직 조회하지 못했어요. 데이터 연결 상태를 확인해 주세요.")
    elif result["status"] == "error":
        st.warning(f"{category} 검색이 실패해 후보 수를 확인할 수 없어요. 이 상태는 검색 결과가 0곳이라는 뜻이 아닙니다.")
    else:
        if result["partial"]:
            st.warning("일부 검색 페이지만 확인했어요. 아래 목록은 받은 결과만 표시하므로 후보 수가 더 늘어날 수 있어요.")
        if result["rows"]:
            st.dataframe(
                pd.DataFrame(result["rows"]), hide_index=True, use_container_width=True, height=460,
                column_config={
                    "목록 순서": st.column_config.NumberColumn("목록 순서", width="small"),
                    "장소명": st.column_config.TextColumn("장소명", width="medium"),
                    "카카오맵": st.column_config.LinkColumn("카카오맵", display_text="장소·후기 보기"),
                },
                key="ai_candidate_table",
            )
            if result["count"] < 45:
                st.caption(f"이번에 확인한 중복 없는 {result['count']}곳을 표시했어요. 검색 결과나 API 제공 범위에 따라 45곳보다 적을 수 있습니다.")
            if result["received_count"] > 45:
                st.caption(f"확인된 {result['received_count']}곳 중 이 분야의 검색 순서 앞쪽 45곳을 표시했어요.")
        elif result["partial"]:
            st.info("불완전한 검색 응답에서 표시할 장소를 확인하지 못했어요. 데이터 연결 상태를 확인한 뒤 다시 조회해 주세요.")
        else:
            st.info(f"이번 {category} 검색 조건에 맞는 장소 결과가 0건이에요. 다른 후보 분야나 지역을 선택해 보세요.")
    st.divider()
    return {"unresolved": unresolved}


def _business_decimal_tenths(value, label, maximum):
    """소수 첫째 자리까지의 입력을 정수 10분율로 바꿉니다."""
    if isinstance(value, bool):
        raise ValueError(f"{label}에는 숫자를 입력해 주세요.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label}에는 숫자를 입력해 주세요.") from None
    if not math.isfinite(number) or number < 0 or number > maximum:
        raise ValueError(f"{label}은 0~{maximum:g} 사이로 입력해 주세요.")
    tenths = int(round(number * 10))
    if abs(number * 10 - tenths) > 0.000001:
        raise ValueError(f"{label}은 소수 첫째 자리까지만 입력해 주세요.")
    return tenths


def _business_split_amount(amount, weights):
    """일일 총액을 입력 비율대로 배분하면서 원 단위 합계를 보존합니다."""
    amount = _impact_integer(amount, "하루 지출", 10000000)
    if not isinstance(weights, dict) or set(weights) != set(_IMPACT_ITEMS):
        raise ValueError("다섯 업종의 지출 비율을 모두 입력해 주세요.")
    weights = {
        code: _impact_integer(weights[code], f"{label} 지출 비율", 100)
        for code, label in _IMPACT_ITEMS.items()
    }
    if sum(weights.values()) != 100:
        raise ValueError("업종별 지출 비율의 합계를 100%로 맞춰 주세요.")
    amounts = {code: amount * weight // 100 for code, weight in weights.items()}
    remainder = amount - sum(amounts.values())
    order = sorted(weights, key=lambda code: -(amount * weights[code] % 100))
    for code in order[:remainder]:
        amounts[code] += 1
    return amounts


def _business_regional_calculate(settings):
    """지역 관리자가 입력한 가정으로 기존 당일·숙박 지출식을 계산합니다."""
    try:
        if not isinstance(settings, dict):
            raise ValueError("방문객과 지출 조건을 확인해 주세요.")
        visitors = _impact_integer(settings.get("visitors", 0), "추가 방문객", 10000000)
        day_spend = _impact_integer(settings.get("day_spend", 50000), "당일 방문객 한 사람의 지출", 10000000)
        local_pct = _impact_integer(settings.get("local_pct", 80), "이 지역에서 쓰는 비율", 100)
        overnight_pct = _impact_integer(settings.get("overnight_pct", 0), "숙박 여행객 비율", 100)
        avg_nights = _business_decimal_tenths(settings.get("avg_nights", 1), "평균 숙박일", 30) / 10
        overnight_daily = _impact_integer(settings.get("overnight_daily_spend", 50000), "숙박 방문객 한 사람의 하루 지출", 10000000)
        lodging = _impact_integer(settings.get("lodging_per_night", 50000), "한 사람의 1박 숙박비", 10000000)
        supplied_weights = settings.get("industry_weights", {
            "food": 40, "cafe": 12, "activities": 20, "local_transport": 8, "shopping": 20,
        })
        # 배분 함수가 누락·잘못된 비율과 합계 100%를 확인합니다.
        day_costs = _business_split_amount(day_spend, supplied_weights)
        overnight_costs = _business_split_amount(overnight_daily, supplied_weights)
        weights = {code: _impact_integer(supplied_weights[code], label, 100)
                   for code, label in _IMPACT_ITEMS.items()}
        period = str(settings.get("period_label", "선택 기간")).strip() or "선택 기간"
        cleaned = {
            "period_label": period, "visitors": visitors,
            "day_spend": day_spend, "local_pct": local_pct,
            "overnight_pct": overnight_pct, "avg_nights": avg_nights,
            "overnight_daily_spend": overnight_daily, "lodging_per_night": lodging,
            "industry_weights": dict(weights),
        }
        result = _impact_calculate({
            "period_label": period, "visitors": visitors,
            "overnight_pct": overnight_pct, "avg_nights": avg_nights,
            "day_costs": day_costs, "overnight_daily_costs": overnight_costs,
            "lodging_per_night": lodging,
            "local_share_pct": {code: local_pct for code in [*_IMPACT_ITEMS, "lodging"]},
        })
        if not result["ok"]:
            return result
        return {
            **result, "input_settings": cleaned,
            "day_spend": day_spend, "local_pct": local_pct,
            "overnight_daily_spend": overnight_daily, "lodging_per_night": lodging,
            "industry_weights": dict(weights),
        }
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "방문객과 지출 조건을 확인해 주세요."
        return {"ok": False, "error": message}


def _business_merchant_calculate(settings):
    """추가 방문객의 가게 이용 비율과 고객당 결제액으로 추가 매출을 계산합니다."""
    try:
        if not isinstance(settings, dict):
            raise ValueError("방문객과 가게 이용 조건을 확인해 주세요.")
        visitors = _impact_integer(settings.get("visitors", 0), "추가 방문객", 10000000)
        purchase_tenths = _business_decimal_tenths(settings.get("purchase_pct", 3), "우리 가게에서 구매할 비율", 100)
        average_sale = _impact_integer(settings.get("average_sale", 20000), "고객 한 명의 평균 결제액", 10000000)
        period = str(settings.get("period_label", "선택 기간")).strip() or "선택 기간"
        shop_name = str(settings.get("shop_name", "우리 가게")).strip() or "우리 가게"
        customers = _impact_round_ratio(visitors * purchase_tenths, 1000)
        cleaned = {
            "period_label": period, "visitors": visitors, "shop_name": shop_name,
            "purchase_pct": purchase_tenths / 10, "average_sale": average_sale,
        }
        return {
            "ok": True, **cleaned, "customers": customers,
            "extra_revenue": customers * average_sale, "input_settings": dict(cleaned),
        }
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "방문객과 가게 이용 조건을 확인해 주세요."
        return {"ok": False, "error": message}


def _business_scenarios(settings, mode):
    """같은 단가·비율에서 방문객 수만 바꾼 비교이며 실제 전망이 아닙니다."""
    calculators = {"region": _business_regional_calculate, "merchant": _business_merchant_calculate}
    calculate = calculators.get(mode)
    if calculate is None:
        return []
    base = calculate(settings)
    if not base["ok"]:
        return []
    rows = []
    for label, scale in (("방문객 20% 적을 때", 80), ("입력한 조건", 100), ("방문객 20% 많을 때", 120)):
        visitors = _impact_round_ratio(base["visitors"] * scale, 100)
        result = calculate({**base["input_settings"], "visitors": visitors})
        if not result["ok"]:
            continue
        row = {"비교 조건": label, "추가 방문객(명)": visitors}
        if mode == "region":
            row["지역 내 예상 소비액(원)"] = result["local_spend"]
        else:
            row["예상 추가 고객(명)"] = result["customers"]
            row["우리 가게 예상 추가 매출(원)"] = result["extra_revenue"]
        rows.append(row)
    return rows


def _business_export_rows(result, mode, region_text):
    """현재 위젯이 아닌, 마지막 계산 결과의 입력 사본을 CSV 행에 담습니다."""
    if not isinstance(result, dict) or not result.get("ok") or mode not in {"region", "merchant"}:
        return []
    settings = result.get("input_settings")
    if not isinstance(settings, dict):
        return []
    common = {
        "계산 대상": "지역 전체" if mode == "region" else "우리 가게",
        "선택 지역": str(region_text), "분석 기간": settings["period_label"],
        "추가 방문객(명)": settings["visitors"],
        "자료 구분": "사용자가 입력한 가정으로 계산한 예시",
    }
    if mode == "merchant":
        return [{
            **common, "가게 이름": settings["shop_name"],
            "우리 가게에서 구매할 비율(%)": settings["purchase_pct"],
            "고객 한 명의 평균 결제액(원)": settings["average_sale"],
            "예상 추가 고객(명)": result["customers"],
            "우리 가게 예상 추가 매출(원)": result["extra_revenue"],
            "고객 수 계산": "방문객 × 구매 비율, 0.5명 이상 올림 반올림",
            "매출 기준": "비용을 빼기 전 금액, 방문객 한 명당 이용 1회 가정",
        }]
    inputs = {
        "당일 방문객 한 사람의 지출(원)": settings["day_spend"],
        "이 지역에서 쓰는 비율(%)": settings["local_pct"],
        "숙박 여행객 비율(%)": settings["overnight_pct"],
        "숙박 방문객(명)": result["overnight_people"],
        "평균 숙박일(박)": settings["avg_nights"],
        "숙박 방문객 한 사람의 하루 지출(원)": settings["overnight_daily_spend"],
        "한 사람의 1박 숙박비(원)": settings["lodging_per_night"],
        "계산 전체 지출(원)": result["total_spend"],
        "계산 지역 내 예상 소비액(원)": result["local_spend"],
        "계산 지역 밖 지출(원)": result["outside_spend"],
    }
    codes = {label: code for code, label in _IMPACT_ITEMS.items()}
    rows = []
    for row in result["rows"]:
        code = codes.get(row["항목"])
        rows.append({
            **common, **inputs,
            "숙박비 외 일일 지출 배분(%)": settings["industry_weights"][code] if code else "숙박비 별도 계산",
            **dict(row),
        })
    return rows


def _business_render_restore_inputs(mode):
    """메뉴 이동으로 없어진 위젯은 마지막으로 계산한 입력값으로 복원합니다."""
    memory = st.session_state.get("business_input_memory", {})
    if not isinstance(memory, dict):
        memory = {}
    common = memory.get("common", {})
    saved = memory.get(mode, {})
    common = common if isinstance(common, dict) else {}
    saved = saved if isinstance(saved, dict) else {}
    defaults = {
        "business_period": common.get("period_label", "지역 행사 기간"),
        "business_visitors": common.get("visitors", 1000),
    }
    if mode == "region":
        defaults.update({
            "business_day_spend": saved.get("day_spend", 50000),
            "business_local_pct": saved.get("local_pct", 80),
            "business_overnight_pct": saved.get("overnight_pct", 0),
            "business_avg_nights": float(saved.get("avg_nights", 1.0)),
            "business_overnight_daily_spend": saved.get("overnight_daily_spend", 50000),
            "business_lodging_per_night": saved.get("lodging_per_night", 50000),
        })
        weights = saved.get("industry_weights", {})
        weights = weights if isinstance(weights, dict) else {}
        for code, default in {"food": 40, "cafe": 12, "activities": 20, "local_transport": 8, "shopping": 20}.items():
            defaults["business_weight_" + code] = weights.get(code, default)
    else:
        defaults.update({
            "business_shop_name": saved.get("shop_name", ""),
            "business_purchase_pct": float(saved.get("purchase_pct", 3.0)),
            "business_average_sale": saved.get("average_sale", 20000),
        })
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _business_render_region_result(result, boundary):
    st.subheader("지역 전체 예상 소비 결과")
    st.metric("지역 안에서 쓸 예상 추가 소비액", f"{result['local_spend']:,}원")
    visitors, average = st.columns(2)
    visitors.metric("예상 추가 방문객", f"{result['visitors']:,}명")
    average.metric("방문객 1인당 지역 소비액 · 약", f"{result['per_visitor_local']:,}원")
    if result["visitors"]:
        st.success(
            f"{result['period_label']}에 방문객이 {result['visitors']:,}명 더 오면, "
            f"{boundary} 안에서 약 {result['local_spend']:,}원을 쓴다는 계산이에요."
        )
    else:
        st.info("추가 방문객이 0명이므로 지역 소비액과 1인당 금액도 0원이에요.")
    st.markdown("#### 어느 업종에서 쓰일까요?")
    labels = {"식비": "음식점", "카페·간식": "카페·간식", "입장·체험": "관광·체험",
              "현지 교통": "현지 교통", "쇼핑·기타": "쇼핑·기타", "숙박비": "숙박"}
    rows = [{"업종": labels.get(row["항목"], row["항목"]),
             "지역 내 예상 소비액": f"{row['지역 내 지출(원)']:,}원"} for row in result["rows"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("음식점·카페 등의 금액은 입력한 업종 비율로 나누고, 숙박비는 따로 계산했어요.")


def _business_render_merchant_result(result, boundary):
    shop = result["shop_name"] or "우리 가게"
    st.subheader("우리 가게 예상 매출 결과")
    revenue, customers = st.columns(2)
    revenue.metric("우리 가게 예상 추가 매출", f"{result['extra_revenue']:,}원")
    customers.metric("예상 추가 고객", f"{result['customers']:,}명")
    if result["visitors"]:
        st.success(
            f"{boundary}의 추가 방문객 {result['visitors']:,}명 중 "
            f"{result['purchase_pct']:g}%가 {shop}에서 구매한다면, "
            f"추가 고객은 약 {result['customers']:,}명, 추가 매출은 약 {result['extra_revenue']:,}원이에요."
        )
    else:
        st.info("추가 방문객이 0명이므로 예상 추가 고객과 매출도 0이에요.")
    st.caption("방문객 한 명이 한 번 구매한다고 가정한 계산이며, 매출은 비용을 빼기 전 금액이에요.")


def _business_render_result_details(result, mode, boundary):
    settings = result["input_settings"]
    with st.expander("계산에 사용한 조건과 계산식 보기"):
        st.write(f"선택 지역: {boundary}")
        st.write(f"계산 기간: {result['period_label']} · 추가 방문객 {result['visitors']:,}명")
        st.caption("기간 이름은 방문객을 집계하는 기준이에요. 기간 이름을 바꿔도 방문객 수나 지출을 자동으로 곱하지 않습니다.")
        if mode == "region":
            condition_rows = [
                {"입력 조건": "당일 방문객 한 사람의 하루 지출", "값": f"{settings['day_spend']:,}원"},
                {"입력 조건": "선택 지역 안에서 쓰는 비율", "값": f"{settings['local_pct']}%"},
                {"입력 조건": "숙박 여행객 비율", "값": f"{settings['overnight_pct']}%"},
                {"입력 조건": "숙박 여행객의 평균 숙박일", "값": f"{settings['avg_nights']:g}박"},
                {"입력 조건": "숙박 여행객 한 사람의 하루 지출 · 숙박비 제외", "값": f"{settings['overnight_daily_spend']:,}원"},
                {"입력 조건": "한 사람의 1박 숙박비", "값": f"{settings['lodging_per_night']:,}원"},
            ]
            st.dataframe(pd.DataFrame(condition_rows), hide_index=True, use_container_width=True)
            st.write(f"당일 방문객 {result['day_people']:,}명은 하루 지출을 한 번 반영해요.")
            st.write(
                f"숙박 여행객 {result['overnight_people']:,}명은 평균 {result['avg_nights']:g}박에 "
                "하루를 더한 여행 기간의 일일 지출과, 숙박한 횟수만큼의 숙박비를 계산해요."
            )
            st.caption("예를 들어 2박 3일이면 식사·카페 등은 3일, 숙박비는 2박을 반영해요. 같은 사람을 당일객과 숙박객 양쪽에 더하지 않습니다.")
            st.write(f"계산한 여행 지출 합계: {result['total_spend']:,}원")
            st.write(f"그중 선택 지역 안: {result['local_spend']:,}원 · 지역 밖: {result['outside_spend']:,}원")
            st.caption(
                f"식사·카페·교통·쇼핑과 숙박비 모두에 선택 지역 안에서 쓰는 비율 {settings['local_pct']}%를 한 번씩 적용했어요. "
                "숙박 여행객도 인근 지역 숙소를 이용할 수 있다는 가정입니다."
            )
            weights = settings["industry_weights"]
            weight_labels = {"food": "음식점", "cafe": "카페·간식", "activities": "관광·체험", "local_transport": "현지 교통", "shopping": "쇼핑·기타"}
            st.caption("일일 지출을 나눈 비율: " + " · ".join(f"{weight_labels[code]} {weights[code]}%" for code in weight_labels))
            st.caption("숙박 여행객 수는 0.5명 이상을 올려 정수로 반올림하고, 지출은 항목별 원 단위로 반올림한 뒤 합산해요.")
            st.caption("지역 소비액은 추가 방문객 집단의 지출을 합친 값이며, 행사·홍보 비용을 뺀 이익이나 실제 측정한 매출이 아니에요.")
        else:
            st.write(f"가게 이름: {result['shop_name'] or '우리 가게'}")
            st.write(f"우리 가게에서 구매할 비율: {result['purchase_pct']:g}%")
            st.write(f"고객 한 사람이 쓰는 평균 금액: {result['average_sale']:,}원")
            st.write(f"예상 추가 고객 = 추가 방문객 {result['visitors']:,}명 × 구매 비율 {result['purchase_pct']:g}% → 약 {result['customers']:,}명")
            st.write(f"예상 추가 매출 = 고객 {result['customers']:,}명 × {result['average_sale']:,}원 = {result['extra_revenue']:,}원")
            st.caption("고객 수는 0.5명 이상을 올려 정수로 반올림한 다음 매출을 계산해요. 구매 비율과 고객당 금액은 직접 입력한 가정이며, 같은 방문객의 반복 구매는 별도로 더하지 않습니다.")
            st.caption("한 가게의 비용을 빼기 전 추가 매출을 계산해요. 지역 전체 소비액을 가게 수로 똑같이 나눈 금액이 아닙니다.")

    scenarios = _business_scenarios(settings, mode)
    with st.expander("방문객이 달라지면 얼마나 달라질까요?"):
        st.caption("나머지 조건을 그대로 두고, 추가 방문객만 20% 적을 때·입력한 인원·20% 많을 때로 비교해요. 실제 전망이나 발생 확률은 아니에요.")
        st.dataframe(pd.DataFrame(scenarios), hide_index=True, use_container_width=True)

    with st.expander("계산 결과 저장하기"):
        st.caption("마지막으로 계산한 지역·기간·입력 조건과 결과를 함께 저장해요.")
        st.download_button(
            "계산 결과와 입력 조건 저장 · CSV",
            _impact_csv(_business_export_rows(result, mode, boundary)),
            f"villageon_{mode}_spending.csv", "text/csv",
            key="business_result_download_" + mode, use_container_width=True,
        )
        scenario_conditions = {
            "계산 대상": "지역 전체" if mode == "region" else "우리 가게",
            "선택 지역": boundary, "기간": result["period_label"],
            "입력한 기준 방문객(명)": settings["visitors"],
            "자료 구분": "입력 조건을 유지하고 방문객 수만 바꾼 가정 비교",
        }
        if mode == "region":
            scenario_conditions.update({
                "당일 방문객 한 사람의 지출(원)": settings["day_spend"],
                "이 지역에서 쓰는 비율(%)": settings["local_pct"],
                "숙박 여행객 비율(%)": settings["overnight_pct"],
                "평균 숙박일(박)": settings["avg_nights"],
                "숙박 방문객 한 사람의 하루 지출(원)": settings["overnight_daily_spend"],
                "한 사람의 1박 숙박비(원)": settings["lodging_per_night"],
            })
            for code, name in _IMPACT_ITEMS.items():
                scenario_conditions[name + " 일일 지출 배분(%)"] = settings["industry_weights"][code]
        else:
            scenario_conditions.update({
                "가게 이름": settings["shop_name"],
                "우리 가게에서 구매할 비율(%)": settings["purchase_pct"],
                "고객 한 명의 평균 결제액(원)": settings["average_sale"],
            })
        scenario_rows = [{**scenario_conditions, **row} for row in scenarios]
        st.download_button(
            "방문객 비교 결과 저장 · CSV", _impact_csv(scenario_rows),
            f"villageon_{mode}_comparison.csv", "text/csv",
            key="business_scenario_download_" + mode, use_container_width=True,
        )


def render_impact_simulator(region, analysis, local_data=None):
    boundary = location_text(region)
    region_key = (str(region.get("region_code", "")), boundary)
    st.caption("상인·상인회·시·군·구 담당자가 방문객 증가에 따른 소비와 매출을 살펴보는 계산이에요.")
    labels = ["지역 전체 소비 효과", "우리 가게 예상 매출"]
    if st.session_state.get("business_mode_label") not in labels:
        saved_mode = st.session_state.get("business_mode_saved", labels[0])
        st.session_state["business_mode_label"] = saved_mode if saved_mode in labels else labels[0]
    label = st.radio("어떤 결과를 보고 싶나요?", labels, horizontal=True, key="business_mode_label")
    st.session_state["business_mode_saved"] = label
    mode = "region" if label == labels[0] else "merchant"
    context = (region_key, mode)
    if st.session_state.get("business_result_context") != context:
        st.session_state.pop("business_result", None)
        st.session_state["business_result_context"] = context
    _business_render_restore_inputs(mode)

    if mode == "region":
        st.caption("지역 관리자·상인회용 · 추가 방문객이 이 지역에서 쓸 돈과 업종별 소비액을 계산해요.")
    else:
        st.caption("상인용 · 추가 방문객 중 우리 가게의 고객이 될 인원과 추가 매출을 계산해요.")
    st.caption("처음 보이는 숫자는 입력 예시예요. 입력한 가정에 따른 계산이며 실제 통계나 AI 예측은 아니에요.")

    with st.form("business_simulator_form", enter_to_submit=False):
        period_col, visitors_col = st.columns(2)
        with period_col:
            period = st.text_input("어느 기간을 살펴볼까요?", max_chars=80, key="business_period",
                                   help="예: 가을 축제 기간, 다음 달. 이 기간에 추가로 방문하는 인원을 입력해요.")
        with visitors_col:
            visitors = st.number_input("이 기간에 방문객이 몇 명 더 올까요?", min_value=0, max_value=8000000,
                                        step=100, key="business_visitors")
        st.caption("현재 방문객에 더해질 인원이에요. 같은 사람은 한 번만 세고, 기간에 맞는 추가 방문객을 입력해 주세요.")
        settings = {"period_label": period, "visitors": visitors}
        if mode == "region":
            spend_col, share_col = st.columns(2)
            with spend_col:
                day_spend = st.number_input("당일 방문객 1명이 하루에 쓸 돈 (원)", min_value=0, max_value=10000000,
                                             step=1000, key="business_day_spend")
            with share_col:
                local_pct = st.slider("전체 지출 중 선택 지역 안에서 쓸 비율 (%)", min_value=0, max_value=100,
                                       step=1, key="business_local_pct")
            st.caption("식사·카페·체험·현지 교통·쇼핑을 합친 금액이에요. 80%라면 쓴 돈 10,000원 중 8,000원을 선택 지역의 가게에서 쓴다는 가정이에요.")
            with st.expander("숙박 방문객도 함께 계산하기 · 선택"):
                overnight_pct = st.slider("방문객 중 숙박 여행객은 몇 %인가요?", min_value=0, max_value=100,
                                           step=1, key="business_overnight_pct")
                st.caption("모두 당일 방문객이면 0%로 두세요. 30%라면 100명 중 30명은 숙박 여행객, 나머지 70명은 당일 방문객으로 계산해요.")
                avg_nights = st.number_input("숙박 여행객은 평균 몇 박을 하나요?", min_value=1.0, max_value=30.0,
                                             step=0.1, format="%.1f", key="business_avg_nights")
                overnight_daily = st.number_input("숙박 여행객 1명이 하루에 쓸 돈 · 숙박비 제외 (원)", min_value=0,
                                                    max_value=10000000, step=1000, key="business_overnight_daily_spend")
                lodging = st.number_input("한 사람의 1박 숙박비 (원)", min_value=0, max_value=10000000,
                                          step=1000, key="business_lodging_per_night")
                st.caption("객실 1박 100,000원을 두 사람이 나누면 50,000원을 넣어요. 숙박 여행객이 0%일 때는 이 숙박 관련 금액을 더하지 않아요.")
            weights = {}
            with st.expander("업종별로 나누는 비율 조정 · 선택"):
                st.caption("숙박비를 제외한 하루 지출을 아래 비율로 나눠요. 합계는 100%로 맞춰 주세요. 업종별 비율도 직접 정하는 가정입니다.")
                columns = st.columns(2)
                weight_labels = {"food": "음식점", "cafe": "카페·간식", "activities": "관광·체험",
                                 "local_transport": "현지 교통", "shopping": "쇼핑·기타"}
                for index, (code, name) in enumerate(weight_labels.items()):
                    with columns[index % 2]:
                        weights[code] = st.number_input(name + "에 쓸 비율 (%)", min_value=0, max_value=100,
                                                       step=1, key="business_weight_" + code)
                st.caption("입력한 비율의 합계는 계산 버튼을 누를 때 확인해요.")
            settings.update({
                "day_spend": day_spend, "local_pct": local_pct, "overnight_pct": overnight_pct,
                "avg_nights": avg_nights, "overnight_daily_spend": overnight_daily,
                "lodging_per_night": lodging, "industry_weights": weights,
            })
            submitted = st.form_submit_button("지역 소비 효과 계산하기", type="primary", use_container_width=True)
        else:
            shop_name = st.text_input("가게 이름 · 선택", max_chars=80, key="business_shop_name")
            share_col, sale_col = st.columns(2)
            with share_col:
                purchase_pct = st.number_input("추가 방문객 중 우리 가게에서 구매할 비율 (%)", min_value=0.0,
                                                max_value=100.0, step=0.1, format="%.1f", key="business_purchase_pct")
            with sale_col:
                average_sale = st.number_input("고객 한 사람이 쓰는 평균 금액 (원)", min_value=0,
                                                max_value=10000000, step=1000, key="business_average_sale")
            st.caption("구매 비율 3%는 지역에 더 온 방문객 100명 중 3명이 우리 가게에서 구매한다는 가정이에요.")
            settings.update({"shop_name": shop_name, "purchase_pct": purchase_pct, "average_sale": average_sale})
            submitted = st.form_submit_button("우리 가게 예상 매출 계산하기", type="primary", use_container_width=True)

    if submitted:
        result = _business_regional_calculate(settings) if mode == "region" else _business_merchant_calculate(settings)
        if not result["ok"]:
            st.session_state.pop("business_result", None)
            st.error(result["error"])
            return
        snapshot = dict(result["input_settings"])
        memory = dict(st.session_state.get("business_input_memory", {}))
        memory["common"] = {"period_label": snapshot["period_label"], "visitors": snapshot["visitors"]}
        memory[mode] = snapshot
        st.session_state["business_input_memory"] = memory
        st.session_state["business_result"] = {"region_key": region_key, "mode": mode, "result": result}

    saved = st.session_state.get("business_result")
    if not saved or saved.get("region_key") != region_key or saved.get("mode") != mode:
        st.info("조건을 입력한 뒤 계산 버튼을 눌러 주세요.")
        return
    result = saved["result"]
    st.divider()
    st.caption(f"마지막 계산 기준 · {boundary} · {result['period_label']} · 추가 방문객 {result['visitors']:,}명")
    if mode == "region":
        settings = result["input_settings"]
        st.caption(f"당일 1인 지출 {settings['day_spend']:,}원 · 지역 안에서 쓸 비율 {settings['local_pct']}% · 숙박 여행객 {settings['overnight_pct']}%")
    else:
        st.caption(f"우리 가게 구매 비율 {result['purchase_pct']:g}% · 고객당 평균 {result['average_sale']:,}원")
    st.caption("입력값을 바꾼 뒤에는 계산 버튼을 다시 눌러 주세요. 아래 결과와 저장 파일은 마지막 계산 조건을 기준으로 해요.")
    if mode == "region":
        _business_render_region_result(result, boundary)
    else:
        _business_render_merchant_result(result, boundary)
    _business_render_result_details(result, mode, boundary)


def render_consumption_simulator(region):
    st.title("지역 소비 시뮬레이터")
    st.caption("선택 지역 · " + location_text(region))
    render_impact_simulator(region, {}, None)


"""장바구니 장소 정리와 일정 작성. 외부 호출이나 세션 변경이 없는 계산 함수."""

import hashlib
import math
import re


_CART_CATEGORIES = ("맛집", "카페", "관광지", "숙박", "학교", "공원", "문화", "체험")
_CART_DEFAULT_MINUTES = {
    "맛집": 60, "카페": 45, "관광지": 90, "숙박": 30,
    "학교": 45, "공원": 60, "문화": 90, "체험": 120,
}


def _cart_text(value):
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    value = str(value).strip()
    return "" if value.lower() in {"nan", "none", "null", "<na>"} else value


def _cart_point(lat, lon):
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError, OverflowError):
        return None
    if math.isfinite(lat) and math.isfinite(lon) and 33 <= lat <= 38.7 and 124 <= lon <= 132:
        return lat, lon
    return None


def _cart_normalize_place(row, region=None):
    """DataFrame 행/카카오 응답/이미 정리한 장소를 같은 표현으로 바꿉니다.

    이름이 없는 항목은 None입니다. 카카오 ID가 있으면 ID를 우선하며,
    좌표가 없는 실제 장소도 목록에서 지우지 않습니다.
    """
    if not isinstance(row, dict):
        return None
    region = region if isinstance(region, dict) else {}
    name = _cart_text(row.get("name")) or _cart_text(row.get("place_name"))
    if not name or name in {"이름 정보 없음", "이름 없음"}:
        return None
    address = (_cart_text(row.get("address")) or _cart_text(row.get("road_address_name"))
               or _cart_text(row.get("address_name")))
    place_id = _cart_text(row.get("place_id")) or _cart_text(row.get("id"))
    if place_id.endswith(".0") and place_id[:-2].isdigit():
        place_id = place_id[:-2]
    if not re.fullmatch(r"[0-9]+", place_id):
        place_id = ""
    url = _cart_text(row.get("url")) or _cart_text(row.get("place_url"))
    match = re.fullmatch(r"https?://place\.map\.kakao\.com/([0-9]+)/?", url)
    if not place_id and match:
        place_id = match.group(1)
    if not place_id:
        old_identity = _cart_text(row.get("identity"))
        old_match = re.fullmatch(r"(?:https?://place\.map\.kakao\.com/|kakao:)([0-9]+)/?", old_identity)
        if old_match:
            place_id = old_match.group(1)
    url = f"https://place.map.kakao.com/{place_id}" if place_id else ""
    identity = url or "place:" + hashlib.sha256(f"{name}|{address}".encode("utf-8")).hexdigest()[:24]
    categories = []
    raw_categories = row.get("categories", [])
    if isinstance(raw_categories, str):
        raw_categories = [raw_categories]
    if isinstance(raw_categories, (list, tuple)):
        categories = [value for value in raw_categories if value in _CART_CATEGORIES]
    main_category = _cart_text(row.get("main_category"))
    category_text = _cart_text(row.get("category")) or _cart_text(row.get("category_name"))
    if main_category not in _CART_CATEGORIES:
        group_codes = {"FD6": "맛집", "CE7": "카페", "AD5": "숙박", "SC4": "학교", "AT4": "관광지"}
        main_category = group_codes.get(_cart_text(row.get("category_group_code")), "")
    if not main_category:
        main_category = next((value for value in _CART_CATEGORIES if value == category_text), "")
    if not main_category:
        hints = (("카페", "카페"), ("숙박", "숙박"), ("호텔", "숙박"), ("학교", "학교"),
                 ("음식점", "맛집"), ("공원", "공원"), ("문화", "문화"), ("체험", "체험"))
        main_category = next((category for word, category in hints if word in category_text), "")
    main_category = main_category or (categories[0] if categories else "관광지")
    categories = list(dict.fromkeys([main_category, *categories]))
    point = _cart_point(row.get("lat", row.get("y")), row.get("lon", row.get("x")))
    region_label = _cart_text(row.get("region_label")) or " ".join(
        _cart_text(region.get(key)) for key in ("sido", "sigungu", "eup") if _cart_text(region.get(key))
    )
    return {
        "identity": identity, "place_id": place_id, "name": name, "address": address,
        "phone": _cart_text(row.get("phone")), "url": url,
        "lat": point[0] if point else None, "lon": point[1] if point else None,
        "categories": categories, "main_category": main_category,
        "category": category_text or main_category, "region_label": region_label,
        "region_code": _cart_text(row.get("region_code")) or _cart_text(region.get("region_code")),
    }


def _cart_kind(place):
    category = place.get("main_category", "")
    return {"숙박": "lodging", "맛집": "meal", "카페": "cafe"}.get(category, "visit")


def _cart_integer(value, default, minimum, maximum):
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("숫자 입력을 확인해 주세요.")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("숫자 입력을 확인해 주세요.") from None
    if not math.isfinite(number) or not number.is_integer() or not minimum <= number <= maximum:
        raise ValueError("숫자 입력 범위를 확인해 주세요.")
    return int(number)


def _cart_distance(a, b):
    first = _cart_point(a.get("lat"), a.get("lon")) if a else None
    second = _cart_point(b.get("lat"), b.get("lon")) if b else None
    if first is None or second is None:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, [*first, *second])
    q = math.sin((lat2 - lat1) / 2) ** 2
    q += math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, q))))


def _cart_island_group(place):
    if not place:
        return ""
    text = " ".join(_cart_text(place.get(key)) for key in ("address", "region_label"))
    for token in ("울릉", "백령", "대청", "소청", "연평", "추자", "우도"):
        if token in text:
            return token
    point = _cart_point(place.get("lat"), place.get("lon"))
    if not text.strip() and point is None:
        return ""
    return "제주" if "제주" in text or (point and 33.0 <= point[0] <= 33.75 and 126.0 <= point[1] <= 127.0) else "육지"


def _cart_transfer(previous, destination, mode):
    """실제 길찾기가 아닌 이동 여유. 확인된 도서 간 연결은 자동 육로 계산하지 않습니다."""
    if previous is None:
        return 0, ""
    a, b = _cart_island_group(previous), _cart_island_group(destination)
    if a and b and a != b:
        return None, "항공·배편이 필요한 구간은 자동 시간표에 연결하지 않았어요. 같은 이동권역의 장소로 나눠 주세요."
    distance = _cart_distance(previous, destination)
    if distance is None:
        return 15, "좌표가 없는 구간은 이동 여유 15분을 임시로 넣었어요. 실제 이동시간을 확인해 주세요."
    if previous.get("identity") and previous.get("identity") == destination.get("identity"):
        return 0, ""
    speed, extra = {"자가용": (30, 5), "대중교통": (20, 10), "도보": (4, 0)}[mode]
    minutes = max(5, int(math.ceil((distance * 1.3 / speed * 60 + extra) / 5) * 5))
    return minutes, f"이전 장소에서 이동 약 {minutes}분 가정 · 직선거리 {distance:.1f}km에 우회·이동 여유를 반영한 예상이에요."


def _cart_clock(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _cart_build_plan(items, settings):
    """선택한 장소를 1~3일에 배치하고, 빠진 장소를 이유와 함께 돌려줍니다.

    days, start_minutes, end_minutes, order, travel_mode, lodging_id,
    duration_overrides를 받습니다. 시간은 여행지 도착 이후 기준입니다.
    자동으로 넣는 식사·미선택 숙소는 실제 장소를 지어내지 않고 직접 선택으로 표시합니다.
    """
    settings = settings if isinstance(settings, dict) else {}
    result = {"status": "ready", "source": "cart", "message": "", "days": 1,
              "interests": [], "itinerary": [], "selected_places": [], "warnings": [],
              "unscheduled": [], "lodging": None, "lodging_nights": 0,
              "missing_slots": 0, "uncovered_by_day": {}, "cart_place_count": 0,
              "scheduled_place_count": 0, "region_labels": [], "duplicates_removed": 0}
    try:
        days = _cart_integer(settings.get("days"), 1, 1, 3)
        start = _cart_integer(settings.get("start_minutes"), 540, 0, 1438)
        end = _cart_integer(settings.get("end_minutes"), 1200, 1, 1439)
    except ValueError as exc:
        return {**result, "status": "invalid", "message": str(exc)}
    result.update(days=days, lodging_nights=days - 1)
    if end - start < 60:
        return {**result, "status": "invalid", "message": "하루 활동 시간은 시작부터 종료까지 최소 1시간으로 정해 주세요. 날짜를 넘기는 시간표는 지원하지 않아요."}
    if not isinstance(items, (list, tuple)):
        return {**result, "status": "invalid", "message": "장바구니 목록을 확인해 주세요."}
    by_id, invalid_count = {}, 0
    for item in items:
        place = _cart_normalize_place(item)
        if place is None:
            invalid_count += 1
            continue
        identity = place["identity"]
        if identity in by_id:
            result["duplicates_removed"] += 1
            old = by_id[identity]
            old["categories"] = list(dict.fromkeys([*old["categories"], *place["categories"]]))
            if old["lat"] is None and place["lat"] is not None:
                old["lat"], old["lon"] = place["lat"], place["lon"]
            continue
        by_id[identity] = place
    places = list(by_id.values())
    result["cart_place_count"] = len(places)
    result["region_labels"] = list(dict.fromkeys(p["region_label"] for p in places if p["region_label"]))
    if invalid_count:
        result["warnings"].append(f"이름 정보를 확인할 수 없는 {invalid_count}개 항목은 장소로 사용할 수 없어요. 콘텐츠 탐색에서 다시 담아 주세요.")
    if not places:
        return {**result, "status": "empty", "message": "콘텐츠 탐색에서 가고 싶은 장소를 먼저 장바구니에 담아 주세요."}
    if len(places) > 60:
        result["unscheduled"] = [{**p, "reason": "한 번에 계획할 수 있는 60곳을 초과했어요."} for p in places]
        return {**result, "status": "invalid", "message": "장바구니는 한 여행에 최대 60곳까지 계획할 수 있어요. 장소를 줄여 주세요."}
    mode = settings.get("travel_mode", "대중교통")
    if mode not in {"대중교통", "자가용", "도보"}:
        return {**result, "status": "invalid", "message": "이동수단을 다시 선택해 주세요."}
    order = settings.get("order", "가까운 순서")
    if order not in {"가까운 순서", "담은 순서"}:
        return {**result, "status": "invalid", "message": "방문 순서를 다시 선택해 주세요."}
    overrides = settings.get("duration_overrides", {})
    if not isinstance(overrides, dict):
        return {**result, "status": "invalid", "message": "장소별 머무는 시간을 확인해 주세요."}
    durations = {}
    try:
        for place in places:
            durations[place["identity"]] = _cart_integer(
                overrides.get(place["identity"]), _CART_DEFAULT_MINUTES[place["main_category"]], 15, 480)
    except ValueError:
        return {**result, "status": "invalid", "message": "장소별 머무는 시간은 15~480분 범위로 입력해 주세요."}
    hotels = [p for p in places if _cart_kind(p) == "lodging"]
    lodging_id = _cart_text(settings.get("lodging_id"))
    lodging = None
    if days > 1 and hotels:
        lodging = next((p for p in hotels if p["identity"] == lodging_id), None) if lodging_id else hotels[0]
        if lodging is None:
            return {**result, "status": "invalid", "message": "선택한 숙소가 장바구니에 없어요. 숙소를 다시 선택해 주세요."}
    result["lodging"] = lodging
    for hotel in hotels:
        if lodging is None or hotel["identity"] != lodging["identity"]:
            reason = ("당일치기는 숙박 일정에 넣지 않아요." if days == 1
                      else "여행 내내 같은 숙소를 사용하므로 다른 숙소 후보는 일정에서 제외했어요.")
            result["unscheduled"].append({**hotel, "reason": reason})
    remaining = [p for p in places if _cart_kind(p) != "lodging"]
    if not remaining and days == 1:
        return {**result, "status": "no_visits", "message": "당일치기로 방문할 장소를 담아 주세요. 숙박 장소만 담겨 있어요."}
    result["warnings"].append("시간표는 여행지에 도착한 뒤 시작해요. 집에서 출발하고 귀가하는 시간은 별도로 확보해 주세요. 왕복 교통비는 시간표 예산 계산에서 포함할 수 있어요.")
    result["warnings"].append("방문 순서와 이동시간은 좌표·체류시간 가정으로 만든 초안이에요. 영업시간, 휴무, 예약 가능 여부와 실제 교통편은 확인해 주세요.")
    if days > 1 and lodging is None:
        result["warnings"].append("숙소를 담지 않아 숙박은 ‘직접 선택’으로 표시했어요. 한 숙소에서 연박하는 조건이며, 다음 날 이동은 전날 마지막으로 확인된 장소 주변에서 시작하는 가정이에요.")
    if any(p["lat"] is None for p in places):
        result["warnings"].append("좌표가 없는 장소도 시간표에는 남겨 두었어요. 그 구간은 지도 선을 끊고 이동 여유 15분을 가정해요.")
    if len(result["region_labels"]) > 1:
        result["warnings"].append("여러 지역의 장소가 담겨 있어요. 장거리 이동으로 하루에 넣지 못한 장소는 아래 미배치 목록에서 확인할 수 있어요.")
    scheduled, rejected_reasons, last_actual = {}, {}, None
    missing_hotel = {"identity": "", "lat": None, "lon": None, "address": "", "region_label": ""}

    def add(day, at, duration, kind, place=None, label="", note="", transfer=0):
        if place:
            scheduled[place["identity"]] = place
        else:
            result["missing_slots"] += 1
        result["itinerary"].append({
            "일차": day, "순서": 1 + sum(r["일차"] == day for r in result["itinerary"]),
            "예시 시각": _cart_clock(at), "예상 종료": _cart_clock(at + duration),
            "일정": label, "장소": place["name"] if place else "직접 선택",
            "분류": place["main_category"] if place else ("맛집" if kind == "meal" else "숙박" if kind in {"lodging", "lodging_departure"} else ""),
            "반영한 관심사": "장바구니에서 선택" if place else "식사·숙박 시간",
            "주소": place["address"] if place else "", "카카오맵": place["url"] if place else "",
            "안내": note, "_place_id": place["identity"] if place else "", "_kind": kind,
            "_duration_minutes": duration, "_transfer_minutes": transfer,
        })

    for day in range(1, days + 1):
        now = start
        previous = lodging if day > 1 and lodging else last_actual if day > 1 else None
        if day > 1:
            add(day, now, 0, "lodging_departure", lodging,
                "숙소 출발 · 체크아웃" if day == days else "숙소 출발",
                "여행 내내 같은 숙소에서 출발해요. 실제 체크아웃 시각은 숙소에서 확인해 주세요." if lodging else "예약할 같은 숙소에서 출발하는 시간이에요. 숙소 위치는 직접 확인해 주세요.")
        # 활동 시간에 포함되는 점심·저녁을 확보합니다. 실제 식당은 장바구니 항목을 우선합니다.
        meal_targets = [at for at in (750, 1110) if start <= at and at + 45 <= end]
        completed_meals = 0
        selected_today = 0
        target_count = max(1, int(math.ceil(len(remaining) / (days - day + 1))))
        if day == days:
            target_count = len(remaining)

        def night_allowance(from_place):
            if day == days:
                return 0
            # 식당의 위치가 아직 없어도 마지막으로 확인한 장소에서의 복귀 거리를 잃지 않습니다.
            anchor = from_place
            unknown_gap = 0
            if anchor is not None and _cart_point(anchor.get("lat"), anchor.get("lon")) is None and last_actual:
                anchor = last_actual
                unknown_gap = 15
            transfer, _ = _cart_transfer(anchor, lodging or missing_hotel, mode)
            return None if transfer is None else transfer + unknown_gap + 15

        def transfer_to(place):
            anchor = previous
            if (anchor is not None and _cart_point(anchor.get("lat"), anchor.get("lon")) is None
                    and last_actual and _cart_point(place.get("lat"), place.get("lon")) is not None):
                transfer, note = _cart_transfer(last_actual, place, mode)
                if transfer is None:
                    return None, note
                return transfer + 15, note + " 위치 미정 일정을 거쳐 마지막 확인 장소를 이동 기준으로 삼고 여유 15분을 더했어요."
            return _cart_transfer(anchor, place, mode)

        def fits(place, transfer):
            after_meals = max(0, len(meal_targets) - completed_meals - (1 if _cart_kind(place) == "meal" else 0))
            # 식당을 아직 정하지 않은 끼니마다 체류 45분 + 앞뒤 이동 여유를 확보합니다.
            return_trip = night_allowance(place)
            if transfer is None or return_trip is None:
                return False
            return now + transfer + durations[place["identity"]] + after_meals * 75 + return_trip <= end

        while remaining and selected_today < target_count:
            candidates = list(remaining)
            if order == "가까운 순서":
                candidates.sort(key=lambda p: (_cart_distance(previous, p) is None,
                                               _cart_distance(previous, p) or 0))
                if completed_meals < len(meal_targets) and now >= meal_targets[completed_meals] - 45:
                    candidates.sort(key=lambda p: _cart_kind(p) != "meal")
            chosen, chosen_transfer, chosen_note = None, None, ""
            for place in candidates:
                transfer, transfer_note = transfer_to(place)
                if fits(place, transfer):
                    chosen, chosen_transfer, chosen_note = place, transfer, transfer_note
                    break
                rejected_reasons[place["identity"]] = transfer_note if transfer is None else "하루 활동 시간 안에 방문·식사·숙소 복귀를 함께 넣기 어려워요. 여행 기간을 늘리거나 장소별 체류시간을 조정해 주세요."
                if order == "담은 순서":
                    break
            if chosen is None:
                break
            # 식당을 뒤로 미루지 않는 가까운 순서에서는 점심/저녁을 지나기 전에 식사 시간을 배치합니다.
            if (order == "가까운 순서" and _cart_kind(chosen) != "meal"
                    and completed_meals < len(meal_targets)
                    and now + chosen_transfer + durations[chosen["identity"]] > meal_targets[completed_meals] + 30
                    and not any(_cart_kind(p) == "meal" and fits(p, transfer_to(p)[0]) for p in remaining)):
                at = max(now + (15 if previous else 0), meal_targets[completed_meals])
                rest = len(meal_targets) - completed_meals - 1
                allowance = night_allowance(missing_hotel)
                if allowance is not None and at + 45 + rest * 75 + allowance <= end:
                    add(day, at, 45, "meal", label="식사 · 식당 직접 선택",
                        note="장바구니에서 식당을 정하지 못한 끼니예요. 예산에는 식비를 포함해요.", transfer=15 if previous else 0)
                    now, previous = at + 45, missing_hotel
                    completed_meals += 1
                    continue
            kind = _cart_kind(chosen)
            now += chosen_transfer
            note = chosen_note
            if kind == "meal":
                completed_meals = min(len(meal_targets), completed_meals + 1)
            if chosen["main_category"] == "학교":
                note += " 학교 방문은 출입 가능 여부와 방문 절차를 확인해 주세요."
            label = {"meal": "식사·맛집 방문", "cafe": "카페·휴식", "visit": "장소 방문"}[kind]
            add(day, now, durations[chosen["identity"]], kind, chosen, label, note, chosen_transfer)
            now += durations[chosen["identity"]]
            previous = chosen
            # 좌표가 없는 방문지는 지도에는 남기되 마지막으로 확인한 이동 기준점을 덮어쓰지 않습니다.
            if _cart_point(chosen.get("lat"), chosen.get("lon")) is not None:
                last_actual = chosen
            remaining = [p for p in remaining if p["identity"] != chosen["identity"]]
            selected_today += 1
        # 남은 식사 시간은 실제 장소를 지어내지 않고 표시합니다. 마지막 귀가날에도 활동 시간만 사용합니다.
        while completed_meals < len(meal_targets):
            remaining_meals = len(meal_targets) - completed_meals - 1
            transfer = 15 if previous else 0
            allowance = night_allowance(missing_hotel)
            if allowance is None:
                break
            latest = end - 45 - remaining_meals * 75 - allowance
            at = min(max(now + transfer, meal_targets[completed_meals]), latest)
            if at < now + transfer or at + 45 > end:
                result["warnings"].append(f"{day}일차에는 추가 식사 시간을 넣을 여유가 부족해요. 일정과 식비를 확인해 주세요.")
                break
            add(day, at, 45, "meal", label="식사 · 식당 직접 선택",
                note="장바구니에서 식당을 정하지 못한 끼니예요. 예산에는 식비를 포함해요.", transfer=transfer)
            now, previous = at + 45, missing_hotel
            completed_meals += 1
        if day < days:
            transfer, note = transfer_to(lodging or missing_hotel)
            if transfer is None:
                # fits에서 복귀 불가능한 방문을 차단하므로 실제 장소 일정에서는 도달하지 않습니다.
                result["warnings"].append(f"{day}일차 숙소 복귀 교통편을 직접 확인해 주세요.")
                transfer = 0
            check_in = max(now + transfer, start)
            if check_in + 15 > end:
                result["status"] = "no_fit"
                result["message"] = "숙소 복귀까지 활동 시간 안에 넣기 어려워요. 하루 활동 시간을 늘리거나 숙소 가까운 장소로 조정해 주세요."
                result["warnings"].append(f"{day}일차 숙소 도착 예상이 활동 마감을 넘어요. 이 시간표는 조정이 필요해요.")
            add(day, check_in, 15, "lodging", lodging, "숙박", note=(
                f"{days - 1}박 동안 같은 숙소를 이용해요. {note}" if lodging
                else "같은 숙소에서 연박하는 일정이에요. 예약할 숙소와 실제 위치를 직접 선택해 주세요."), transfer=transfer)
            if lodging and _cart_point(lodging.get("lat"), lodging.get("lon")) is not None:
                last_actual = lodging
    for place in remaining:
        result["unscheduled"].append({**place, "reason": rejected_reasons.get(place["identity"], "선택한 여행 기간의 시간표에 넣을 자리가 부족해요. 기간을 늘리거나 방문 장소를 줄여 주세요.")})
    result["selected_places"] = list(scheduled.values())
    result["scheduled_place_count"] = len(scheduled)
    result["scheduled_visit_count"] = sum(_cart_kind(p) != "lodging" for p in scheduled.values())
    if remaining:
        result["warnings"].append(f"담은 방문지 중 {len(remaining)}곳은 시간표에 넣지 못했어요. 미배치 장소와 이유를 확인해 주세요.")
    if result["scheduled_visit_count"] == 0 and remaining:
        result["status"] = "no_fit"
        result["message"] = "담은 방문지를 활동 시간 안에 넣지 못했어요. 장소별 체류시간이나 하루 활동 시간, 여행 기간을 조정해 주세요."
    return result


# ============================================================
# 저장된 여행 시간표로 계산하는 예산
# 실제 요금을 조회하지 않습니다. 사용자가 확인·수정한 단가와 교통비로 계산합니다.
# ============================================================


def _plan_budget_integer(value, label, minimum=0, maximum=10**12):
    if isinstance(value, bool):
        raise ValueError(f"{label}에는 숫자를 입력해 주세요.")
    try:
        number = value if isinstance(value, int) else float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label}에는 숫자를 입력해 주세요.") from None
    if not math.isfinite(number) or (not isinstance(number, int) and not number.is_integer()) or not minimum <= number <= maximum:
        raise ValueError(f"{label}은 {minimum:,}~{maximum:,} 사이의 정수로 입력해 주세요.")
    return int(number)


def _plan_budget_text(value):
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "<na>"} else text


def _plan_budget_point(lat, lon):
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    try:
        point = float(lat), float(lon)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(value) for value in point):
        return None
    return point if 33.0 <= point[0] <= 38.7 and 124.0 <= point[1] <= 132.0 else None


def _plan_budget_row_kind(row):
    """새 장바구니 시간표와 기존 AI 시간표를 같은 비용 종류로 읽습니다."""
    label = _plan_budget_text(row.get("일정"))
    category = _plan_budget_text(row.get("분류"))
    kind = row.get("_kind")
    # 옛 시간표의 '숙박' 분류인 출발 행을 숙박료로 중복 청구하지 않습니다.
    if "체크아웃" in label or "숙소 출발" in label or kind == "lodging_departure":
        return "lodging_departure"
    if kind == "visit" and not row.get("_place_id") and _plan_budget_text(row.get("장소")) in {"", "직접 선택", "자유 시간"}:
        return "free"
    if kind in {"meal", "cafe", "visit", "lodging", "free"}:
        return kind
    if "숙박" in label or (category == "숙박" and "출발" not in label):
        return "lodging"
    if category == "카페":
        return "cafe"
    if category == "맛집" or any(word in label for word in ("식사", "아침", "점심", "저녁")):
        return "meal"
    if category in {"관광지", "공원", "문화", "체험", "학교", "축제"} and row.get("_place_id"):
        return "visit"
    return "free"


def _plan_budget_rows(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("itinerary"), list) or not plan["itinerary"]:
        raise ValueError("먼저 AI 추천이나 장바구니에서 여행 시간표를 만들어 주세요.")
    rows = []
    for index, source_row in enumerate(plan["itinerary"]):
        if not isinstance(source_row, dict):
            raise ValueError("시간표에 읽을 수 없는 일정이 있어요. 시간표를 다시 만들어 주세요.")
        day = _plan_budget_integer(source_row.get("일차", 1), "여행 일차", 1, 30)
        row = dict(source_row)
        row["일차"] = day
        row["_budget_kind"] = _plan_budget_row_kind(row)
        # 같은 장소에 두 번 방문하면 각각의 방문 비용을 조정할 수 있습니다.
        raw_key = f"{day}|{index}|{_plan_budget_text(row.get('_place_id'))}|{_plan_budget_text(row.get('장소'))}"
        row["_budget_row_key"] = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:20]
        rows.append(row)
    days = _plan_budget_integer(plan.get("days", max(row["일차"] for row in rows)), "여행 기간", 1, 30)
    if any(row["일차"] > days for row in rows):
        raise ValueError("시간표의 일차와 여행 기간이 맞지 않아요. 시간표를 다시 만들어 주세요.")
    return rows, days


def _plan_budget_counts(plan):
    rows, days = _plan_budget_rows(plan)
    overnight_days = sorted({row["일차"] for row in rows
                             if row["_budget_kind"] == "lodging" and row["일차"] < days})
    visits = [row for row in rows if row["_budget_kind"] == "visit"]
    return {
        "days": days,
        "meals": sum(row["_budget_kind"] == "meal" for row in rows),
        "cafes": sum(row["_budget_kind"] == "cafe" for row in rows),
        "visits": len(visits),
        "nights": len(overnight_days),
        "overnight_days": overnight_days,
        "visit_rows": visits,
        "rows": rows,
    }


def _plan_budget_endpoints(plan):
    rows, _ = _plan_budget_rows(plan)
    lookup = {place.get("identity"): place for place in plan.get("selected_places", [])
              if isinstance(place, dict) and place.get("identity")}
    stops = []
    for index, row in enumerate(rows):
        place = lookup.get(row.get("_place_id"), {})
        point = _plan_budget_point(place.get("lat"), place.get("lon"))
        if point:
            stops.append({"point": point, "name": _plan_budget_text(row.get("장소")) or _plan_budget_text(place.get("name")),
                          "address": _plan_budget_text(place.get("address")) or _plan_budget_text(row.get("주소")),
                          "day": row["일차"], "time": _plan_budget_text(row.get("예시 시각")),
                          "itinerary_index": index})
    if stops:
        stops[0]["boundary_missing"] = stops[0]["itinerary_index"] > 0
        stops[-1]["boundary_missing"] = stops[-1].get("boundary_missing", False) or stops[-1]["itinerary_index"] < len(rows) - 1
    return (stops[0], stops[-1]) if stops else (None, None)


def _plan_budget_needs_manual_route(plan, origin_text, origin_point=None):
    """확인 가능한 도서 지명·제주 횡단은 육로 추정을 하지 않습니다."""
    texts = [_plan_budget_text(plan.get("region_label")), _plan_budget_text(origin_text)]
    points = []
    for place in plan.get("selected_places", []):
        if isinstance(place, dict):
            texts.extend([_plan_budget_text(place.get("address")), _plan_budget_text(place.get("region_label"))])
            point = _plan_budget_point(place.get("lat"), place.get("lon"))
            if point:
                points.append(point)
    islands = ("울릉", "우도", "추자", "백령", "대청", "소청", "연평", "덕적", "자월",
               "흑산", "홍도", "가거", "청산면", "노화읍", "보길면", "소안면", "금일읍",
               "생일면", "욕지면", "사량면", "한산면")
    if any(word in text for word in islands for text in texts):
        return True
    def is_jeju(point):
        return point is not None and 33.0 <= point[0] <= 33.75 and 126.0 <= point[1] <= 127.0
    if origin_point and points and any(is_jeju(point) != is_jeju(origin_point) for point in points):
        return True
    if not origin_point:
        destination_jeju = any("제주" in text for text in texts[2:]) or "제주" in texts[0]
        if bool("제주" in _plan_budget_text(origin_text)) != destination_jeju:
            return True
    return False


def _plan_budget_transport(plan, settings, origin_point=None):
    counts = _plan_budget_counts(plan)
    people = _plan_budget_integer(settings.get("people", 1), "여행 인원", 1, 50)
    mode = settings.get("mode", "대중교통")
    if mode not in {"대중교통", "자가용"}:
        raise ValueError("교통수단을 다시 선택해 주세요.")
    vehicles = _plan_budget_integer(settings.get("vehicle_count", 1), "차량 수", 1, 20)
    local_daily = _plan_budget_integer(settings.get("local_daily", 8000 if mode == "대중교통" else 15000), "현지 이동비")
    local_units = people if mode == "대중교통" else vehicles
    local_cost = local_daily * counts["days"] * local_units
    method = settings.get("transport_input", "직접 입력")
    if method == "직접 입력":
        amount = _plan_budget_integer(settings.get("manual_amount", 40000), "왕복 교통비")
        basis = settings.get("manual_basis", "1인 왕복")
        units = {"1인 왕복": people, "일행 전체 왕복": 1, "차량 1대 왕복": vehicles}
        if basis not in units or (basis == "차량 1대 왕복" and mode != "자가용"):
            raise ValueError("왕복 교통비의 금액 기준을 다시 선택해 주세요.")
        return {"ok": True, "roundtrip_cost": amount * units[basis], "local_cost": local_cost,
                "basis": f"{basis} {amount:,}원 × {units[basis]} · 이미 왕복 금액이므로 두 배로 계산하지 않아요.",
                "note": "직접 입력한 왕복 교통비를 반영했어요. 기본 금액은 예시이며 실제 예매 요금·주행비로 바꿔 주세요.",
                "local_basis": f"{'1인' if mode == '대중교통' else '차량 1대'} 하루 {local_daily:,}원 × {local_units}{'명' if mode == '대중교통' else '대'} × {counts['days']}일"}
    if method != "거리로 추정":
        raise ValueError("왕복 교통비 계산 방법을 다시 선택해 주세요.")
    if not origin_point or _plan_budget_point(*origin_point) is None:
        raise ValueError("출발지 좌표를 확인하지 못했어요. 주소를 확인하거나 왕복비를 직접 입력해 주세요.")
    if settings.get("air_ferry") or _plan_budget_needs_manual_route(plan, settings.get("origin", ""), origin_point):
        raise ValueError("항공·배편이나 도서 지역이 포함된 이동은 왕복 교통비를 직접 입력해 주세요.")
    first, last = _plan_budget_endpoints(plan)
    if not first or not last:
        raise ValueError("시간표에서 좌표가 있는 방문지를 찾지 못했어요. 왕복 교통비를 직접 입력해 주세요.")
    try:
        factor = float(settings.get("road_factor", 1.3))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("거리 추정 배수를 확인해 주세요.") from None
    if not math.isfinite(factor) or not 1.0 <= factor <= 3.0:
        raise ValueError("거리 추정 배수는 1.0~3.0 사이로 입력해 주세요.")
    out_straight = _budget_haversine(origin_point, first["point"])
    in_straight = _budget_haversine(last["point"], origin_point)
    out_km, in_km = out_straight * factor, in_straight * factor
    unit_cost = _plan_budget_integer(settings.get("km_cost", 150 if mode == "대중교통" else 200), "거리당 예상 비용")
    if mode == "대중교통":
        minimum = _plan_budget_integer(settings.get("minimum_fare", 5000), "편도 최소 운임")
        fare_out = 0 if out_km < 0.01 else max(minimum, math.ceil(out_km * unit_cost))
        fare_in = 0 if in_km < 0.01 else max(minimum, math.ceil(in_km * unit_cost))
        total = (fare_out + fare_in) * people
        basis = f"(1인 가는 편 {fare_out:,}원 + 오는 편 {fare_in:,}원) × {people}명"
    else:
        toll = _plan_budget_integer(settings.get("toll", 10000), "차량 1대 왕복 통행료")
        car_cost = math.ceil((out_km + in_km) * unit_cost) + toll
        total = car_cost * vehicles
        basis = f"차량 1대 왕복 주행·통행료 {car_cost:,}원 × {vehicles}대"
    boundary_note = (" 시간표 맨 앞이나 맨 뒤에 좌표가 없는 일정이 있어 좌표를 확인한 첫·마지막 장소를 대신 사용했어요. 추가 이동은 직접 입력한 왕복비에 반영할 수 있어요."
                     if first.get("boundary_missing") or last.get("boundary_missing") else "")
    return {"ok": True, "roundtrip_cost": total, "local_cost": local_cost, "basis": basis,
            "outbound_km": out_km, "inbound_km": in_km, "first_stop": first["name"], "last_stop": last["name"],
            "note": f"출발지 → {first['name']} / {last['name']} → 출발지를 각각 계산했어요. 직선거리에 {factor:.1f}배를 적용한 가정이며 실제 도로·열차·버스 운임 조회가 아니에요." + boundary_note,
            "local_basis": f"{'1인' if mode == '대중교통' else '차량 1대'} 하루 {local_daily:,}원 × {local_units}{'명' if mode == '대중교통' else '대'} × {counts['days']}일"}


def _plan_budget_calculate(plan, settings, transport=None):
    """시간표를 바꾸지 않고 해당 일정의 비용만 계산하는 순수 함수."""
    try:
        counts = _plan_budget_counts(plan)
        people = _plan_budget_integer(settings.get("people", 1), "여행 인원", 1, 50)
        room_people = _plan_budget_integer(settings.get("room_people", 2), "객실당 인원", 1, 50)
        meal = _plan_budget_integer(settings.get("meal_cost", 12000), "1인 1끼 식비")
        cafe = _plan_budget_integer(settings.get("cafe_cost", 6000), "1인 카페 비용")
        activity = _plan_budget_integer(settings.get("activity_cost", 10000), "1인 방문지 이용료")
        lodging = _plan_budget_integer(settings.get("lodging_cost", 80000), "객실 1개 1박 비용")
        reserve_pct = _plan_budget_integer(settings.get("reserve_pct", 10), "예비비 비율", 0, 100)
        target = _plan_budget_integer(settings.get("target_budget", 0), "전체 여행 예산")
        if transport is None:
            transport = _plan_budget_transport(plan, settings, settings.get("origin_point"))
        if not isinstance(transport, dict) or not transport.get("ok", True):
            raise ValueError("왕복 교통비를 확인하지 못했어요. 계산 조건을 다시 확인해 주세요.")
        roundtrip = _plan_budget_integer(transport.get("roundtrip_cost"), "전체 왕복 교통비", maximum=10**17)
        local = _plan_budget_integer(transport.get("local_cost"), "전체 현지 이동비", maximum=10**17)
        overrides = settings.get("activity_overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("방문지별 이용료를 다시 확인해 주세요.")
        place_costs, activity_total = [], 0
        for row in counts["visit_rows"]:
            default = 0 if _plan_budget_text(row.get("분류")) == "학교" else activity
            unit = _plan_budget_integer(overrides.get(row["_budget_row_key"], default), "방문지별 1인 이용료")
            amount = unit * people
            activity_total += amount
            place_costs.append({"일차": row["일차"], "시각": row.get("예시 시각", ""), "장소": row.get("장소", ""),
                                "1인 예상 이용료(원)": unit, "인원": people, "금액(원)": amount})
        rooms = (people + room_people - 1) // room_people if counts["nights"] else 0
        breakdown = [
            {"항목": "출발지 ↔ 여행지 왕복 교통비", "금액(원)": roundtrip, "계산 기준": transport.get("basis", "일행 전체 왕복 금액")},
            {"항목": "여행지 안에서 이동", "금액(원)": local, "계산 기준": transport.get("local_basis", "일행 전체 현지 이동 금액")},
            {"항목": "식비", "금액(원)": meal * counts["meals"] * people,
             "계산 기준": f"시간표의 식사 {counts['meals']}회 × 1인 {meal:,}원 × {people}명"},
            {"항목": "카페", "금액(원)": cafe * counts["cafes"] * people,
             "계산 기준": f"시간표의 카페 {counts['cafes']}회 × 1인 {cafe:,}원 × {people}명"},
            {"항목": "입장·체험", "금액(원)": activity_total,
             "계산 기준": f"시간표 방문지 {counts['visits']}회의 1인 이용료 합계 × {people}명 (장소별 수정 가능)"},
            {"항목": "숙박", "금액(원)": lodging * rooms * counts["nights"],
             "계산 기준": "당일치기 · 숙박비 없음" if counts["days"] == 1 else f"객실 1개 1박 {lodging:,}원 × {rooms}실 × 시간표의 {counts['nights']}박"},
        ]
        subtotal = sum(row["금액(원)"] for row in breakdown)
        reserve = (subtotal * reserve_pct + 99) // 100
        breakdown.append({"항목": "예비비", "금액(원)": reserve, "계산 기준": f"위 비용 합계 {subtotal:,}원의 {reserve_pct}% · 원 단위 올림"})
        total = subtotal + reserve
        warnings = []
        if counts["nights"] < counts["days"] - 1:
            warnings.append("시간표에 일부 숙박 일정이 없어서 해당 밤의 숙박비가 포함되지 않았어요. 여러 날 여행한다면 숙박 일정을 먼저 확인해 주세요.")
        if not counts["meals"]:
            warnings.append("시간표에 식사 일정이 없어 식비는 0원이에요. 식사 계획이 있다면 시간표에 추가해 주세요.")
        return {"status": "ready", "total": total, "subtotal": subtotal, "reserve": reserve,
                "per_person": (total + people - 1) // people, "people": people, "rooms": rooms,
                "target_budget": target, "remaining": target - total if target > 0 else None,
                "breakdown": breakdown, "place_costs": place_costs,
                "counts": {key: value for key, value in counts.items() if key not in {"rows", "visit_rows"}},
                "transport": dict(transport), "warnings": warnings}
    except (TypeError, ValueError, OverflowError) as exc:
        return {"status": "invalid", "message": str(exc)}


def _plan_budget_plan_key(plan):
    payload = {key: plan.get(key) for key in ("id", "days", "source", "title", "region_label", "itinerary", "selected_places")}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _plan_budget_fingerprint(plan, settings):
    payload = {"plan": _plan_budget_plan_key(plan), "settings": settings}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def render_plan_budget(plan, region, api_key, namespace="plan_cost"):
    """저장된 시간표 스냅샷을 이용하는 모바일 친화적 비용 입력·결과 화면."""
    try:
        counts = _plan_budget_counts(plan)
    except (TypeError, ValueError, OverflowError) as exc:
        st.info(str(exc))
        return
    prefix = f"{namespace}_{_plan_budget_plan_key(plan)[:12]}"
    memory_key, result_key = prefix + "_memory", prefix + "_result"
    memory = dict(st.session_state.get(memory_key, {}))
    defaults = {
        "people": 1, "target_budget": 0, "origin": "", "mode": "대중교통", "transport_input": "직접 입력",
        "manual_amount": 40000, "manual_basis": "1인 왕복", "meal_cost": 12000, "cafe_cost": 6000,
        "activity_cost": 10000, "local_daily": 8000, "reserve_pct": 10, "lodging_cost": 80000,
        "room_people": 2, "vehicle_count": 1, "road_factor": 1.3, "km_cost": 150,
        "minimum_fare": 5000, "toll": 10000, "air_ferry": False,
    }
    # 위젯이 메뉴 이동 때 사라져도 마지막 제출값은 별도 메모리에 남습니다.
    for field, default in defaults.items():
        widget_key = prefix + "_" + field
        if widget_key not in st.session_state:
            st.session_state[widget_key] = memory.get(field, default)
    for field, options in (("mode", ["대중교통", "자가용"]), ("transport_input", ["직접 입력", "거리로 추정"])):
        if st.session_state.get(prefix + "_" + field) not in options:
            st.session_state[prefix + "_" + field] = options[0]

    st.subheader("이 시간표의 여행비는 얼마일까요?")
    st.write(_plan_budget_text(plan.get("title")) or "저장한 여행 시간표")
    region_label = _plan_budget_text(plan.get("region_label")) or location_text(region)
    st.caption(f"{region_label} · {counts['days']}일 · 식사 {counts['meals']}회 · 카페 {counts['cafes']}회 · 방문 {counts['visits']}회 · 숙박 {counts['nights']}박")
    st.caption("기본 금액은 계산용 예시예요. 예매한 교통비와 예상 소비 금액으로 바꾸면 이 시간표의 총예산을 계산해요.")
    c1, c2 = st.columns(2)
    with c1:
        mode = st.radio("교통수단", ["대중교통", "자가용"], horizontal=True, key=prefix + "_mode")
    with c2:
        method = st.radio("왕복 교통비 계산", ["직접 입력", "거리로 추정"], horizontal=True, key=prefix + "_transport_input")
    basis_options = ["1인 왕복", "일행 전체 왕복"] if mode == "대중교통" else ["차량 1대 왕복", "일행 전체 왕복"]
    if st.session_state.get(prefix + "_manual_basis") not in basis_options:
        st.session_state[prefix + "_manual_basis"] = basis_options[0]

    with st.form(prefix + "_form", enter_to_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            people = st.number_input("여행 인원 (명)", min_value=1, max_value=50, step=1, key=prefix + "_people")
        with c2:
            target = st.number_input("사용할 전체 예산 (원) · 0이면 비교 생략", min_value=0, max_value=10**12, step=10000, key=prefix + "_target_budget")
        origin = st.text_input("출발지 주소 또는 역명" + (" · 선택 입력" if method == "직접 입력" else ""),
                               placeholder="예: 서울역, 경기도 수원시 ...", key=prefix + "_origin")
        manual_amount, manual_basis = memory.get("manual_amount", 40000), st.session_state[prefix + "_manual_basis"]
        vehicle_count = memory.get("vehicle_count", 1)
        if mode == "자가용":
            vehicle_count = st.number_input("차량 수 (대)", min_value=1, max_value=20, step=1, key=prefix + "_vehicle_count")
        if method == "직접 입력":
            c1, c2 = st.columns(2)
            with c1:
                manual_basis = st.selectbox("입력할 금액의 기준", basis_options, key=prefix + "_manual_basis")
            with c2:
                manual_amount = st.number_input("가는 편 + 오는 편 교통비 (원)", min_value=0, max_value=10**12, step=1000, key=prefix + "_manual_amount")
            st.caption("왕복 합계로 입력해요. 항공·배편도 포함할 수 있어요. 현지 버스·택시·주차비는 아래에서 따로 계산해요.")
        else:
            st.caption("출발지에서 시간표의 첫 장소까지, 마지막 장소에서 출발지까지의 거리를 각각 추정해요. 실제 운임 조회는 아니에요.")
        with st.expander("식비·카페·숙박비 조정", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                meal = st.number_input("식비 · 1인 1끼 (원)", min_value=0, max_value=10**12, step=1000, key=prefix + "_meal_cost")
                cafe = st.number_input("카페 · 1인 1회 (원)", min_value=0, max_value=10**12, step=1000, key=prefix + "_cafe_cost")
            with c2:
                local = st.number_input("현지 이동 · 1인 하루 (원)" if mode == "대중교통" else "현지 주행·주차 · 차량 1대 하루 (원)",
                                        min_value=0, max_value=10**12, step=1000, key=prefix + "_local_daily")
                reserve = st.number_input("예비비 (%)", min_value=0, max_value=100, step=1, key=prefix + "_reserve_pct")
            lodging, room_people = memory.get("lodging_cost", 80000), memory.get("room_people", 2)
            if counts["nights"]:
                c1, c2 = st.columns(2)
                with c1:
                    lodging = st.number_input("숙박 · 객실 1개 1박 (원)", min_value=0, max_value=10**12, step=10000, key=prefix + "_lodging_cost")
                with c2:
                    room_people = st.number_input("객실 1개당 인원 (명)", min_value=1, max_value=50, step=1, key=prefix + "_room_people")
                st.caption(f"시간표에 있는 {counts['nights']}박만 계산해요. 숙소 출발·체크아웃에는 숙박비를 추가하지 않아요.")
            else:
                st.caption("현재 시간표에는 숙박비를 계산할 밤이 없어요.")
        overrides = {}
        if counts["visit_rows"]:
            with st.expander("방문지별 이용료 조정 · 무료 장소는 0원", expanded=False):
                saved_overrides = memory.get("activity_overrides", {})
                if not isinstance(saved_overrides, dict):
                    saved_overrides = {}
                editor_rows = []
                for row in counts["visit_rows"]:
                    value = saved_overrides.get(row["_budget_row_key"], 0 if row.get("분류") == "학교" else 10000)
                    editor_rows.append({"일차": row["일차"], "시각": row.get("예시 시각", ""), "장소": row.get("장소", ""), "1인 예상 이용료(원)": value})
                edited = st.data_editor(pd.DataFrame(editor_rows), key=prefix + "_activity_editor", hide_index=True,
                                        use_container_width=True, num_rows="fixed", disabled=["일차", "시각", "장소"],
                                        column_config={"1인 예상 이용료(원)": st.column_config.NumberColumn("1인 예상 이용료(원)", min_value=0, max_value=10**12, step=1000, format="%d원")})
                for row, value in zip(counts["visit_rows"], edited["1인 예상 이용료(원)"].tolist()):
                    overrides[row["_budget_row_key"]] = value
                st.caption("표의 금액은 실제 입장료를 조회한 값이 아니에요. 무료 공원·전시 등은 0원으로 바꿔 주세요.")
        road_factor, km_cost, minimum_fare, toll, air_ferry = 1.3, 150 if mode == "대중교통" else 200, 5000, 10000, False
        if method == "거리로 추정":
            with st.expander("거리 추정 조건", expanded=False):
                air_ferry = st.checkbox("항공·배편이 포함돼요", key=prefix + "_air_ferry")
                road_factor = st.number_input("직선거리 대비 이동거리 배수", min_value=1.0, max_value=3.0, step=0.1, key=prefix + "_road_factor")
                km_cost = st.number_input("1인 1km당 운임 가정 (원)" if mode == "대중교통" else "차량 1km당 주행비 가정 (원)",
                                          min_value=0, max_value=100000, step=10, key=prefix + "_km_cost")
                if mode == "대중교통":
                    minimum_fare = st.number_input("1인 편도 최소 운임 가정 (원)", min_value=0, max_value=10**12, step=1000, key=prefix + "_minimum_fare")
                else:
                    toll = st.number_input("차량 1대 왕복 통행료 가정 (원)", min_value=0, max_value=10**12, step=1000, key=prefix + "_toll")
                st.caption("항공·배편은 거리에 따른 육로 비용으로 계산할 수 없어 직접 입력을 사용해야 해요.")
        submitted = st.form_submit_button("이 시간표로 예산 계산", type="primary", use_container_width=True, key=prefix + "_calculate")

    settings = {"people": int(people), "target_budget": int(target), "origin": origin.strip(), "mode": mode,
                "transport_input": method, "manual_amount": manual_amount, "manual_basis": manual_basis,
                "meal_cost": int(meal), "cafe_cost": int(cafe), "activity_cost": 10000, "activity_overrides": overrides,
                "local_daily": int(local), "reserve_pct": int(reserve), "lodging_cost": int(lodging), "room_people": int(room_people),
                "vehicle_count": int(vehicle_count), "road_factor": float(road_factor), "km_cost": int(km_cost),
                "minimum_fare": int(minimum_fare), "toll": int(toll), "air_ferry": bool(air_ferry)}
    # 다른 화면으로 이동한 뒤에도 조건을 복원합니다. 실제 미제출 편집값은 계산 버튼을 눌러 반영합니다.
    st.session_state[memory_key] = settings
    fingerprint = _plan_budget_fingerprint(plan, settings)
    if submitted:
        origin_result = None
        if method == "거리로 추정":
            if not origin.strip():
                result = {"status": "invalid", "message": "거리로 추정하려면 출발지 주소나 역명을 입력해 주세요."}
            elif not api_key:
                result = {"status": "invalid", "message": "출발지 검색 연결이 필요해요. 지금은 왕복 교통비 직접 입력을 사용해 주세요."}
            elif air_ferry:
                result = {"status": "invalid", "message": "항공·배편이나 도서 지역이 포함되면 왕복 교통비를 직접 입력해 주세요."}
            else:
                try:
                    with st.spinner("출발지와 시간표의 첫·마지막 장소를 확인하고 있어요..."):
                        origin_result = _budget_geocode_origin(origin, api_key)
                except Exception:
                    origin_result = None
                point = _plan_budget_point(origin_result.get("lat"), origin_result.get("lon")) if origin_result else None
                if point:
                    result = _plan_budget_calculate(plan, {**settings, "origin_point": point})
                    if result.get("status") == "ready":
                        result["origin_label"] = _plan_budget_text(origin_result.get("label")) or origin.strip()
                else:
                    result = {"status": "invalid", "message": "출발지를 찾지 못했어요. 자세한 주소를 입력하거나 왕복 교통비 직접 입력을 사용해 주세요."}
        else:
            result = _plan_budget_calculate(plan, settings)
        st.session_state[result_key] = {"fingerprint": fingerprint, "result": result}

    saved = st.session_state.get(result_key)
    if not saved:
        st.info("왕복 교통비와 인원을 확인한 뒤 ‘이 시간표로 예산 계산’을 눌러 주세요.")
        return
    if saved.get("fingerprint") != fingerprint:
        st.info("계산 조건이 바뀌었어요. 버튼을 눌러 새 조건을 반영해 주세요.")
        return
    result = saved["result"]
    if result.get("status") != "ready":
        st.error(result.get("message", "계산 조건을 확인해 주세요."))
        return
    st.divider()
    st.subheader("시간표 기준 예상 예산")
    c1, c2 = st.columns(2)
    c1.metric("일행 전체 예상 금액", f"{result['total']:,}원")
    c2.metric("1인당 나눠 부담하면", f"약 {result['per_person']:,}원")
    if result["remaining"] is not None:
        if result["remaining"] >= 0:
            st.success(f"설정한 전체 예산보다 {result['remaining']:,}원 여유가 있어요.")
        else:
            st.warning(f"설정한 전체 예산보다 {-result['remaining']:,}원 초과해요. 단가를 조정하거나 시간표에서 방문지를 줄여 보세요.")
    st.caption(f"{people}명 · 왕복 교통비 포함 · 식사 {counts['meals']}회 / 카페 {counts['cafes']}회 / 방문 {counts['visits']}회 / 숙박 {counts['nights']}박")
    st.dataframe(pd.DataFrame(result["breakdown"]), hide_index=True, use_container_width=True,
                 column_config={"금액(원)": st.column_config.NumberColumn("금액(원)", format="%d원")})
    st.caption("계산은 현재 시간표를 그대로 사용해요. 실시간 가격·예약 가능 여부·실제 이동시간을 확인한 결과는 아니에요.")
    for warning in result["warnings"]:
        st.warning(warning)
    with st.expander("왕복 계산과 방문지 이용료 자세히 보기"):
        if result.get("origin_label"):
            st.write("확인한 출발지: " + result["origin_label"])
        st.write(result["transport"]["note"])
        if "outbound_km" in result["transport"]:
            st.caption(f"가는 편 추정 {result['transport']['outbound_km']:.1f}km / 오는 편 추정 {result['transport']['inbound_km']:.1f}km")
        if result["place_costs"]:
            st.dataframe(pd.DataFrame(result["place_costs"]), hide_index=True, use_container_width=True)
    export_rows = [{"시간표": _plan_budget_text(plan.get("title")), "여행지": region_label, "인원": people,
                    "여행일수": counts["days"], "전체 예상액(원)": result["total"], **row} for row in result["breakdown"]]
    st.download_button("이 시간표 예산표 다운로드", _trip_csv(export_rows), file_name="villageon_schedule_budget.csv",
                       mime="text/csv", key=prefix + "_download", use_container_width=True)


# ============================================================
# 여행 장바구니 · 저장된 시간표 · 이어서 예산 계산
# ============================================================

_TRIP_MENU = ["콘텐츠 탐색", "장바구니", "AI 추천", "예산 여행 코스", "지역 소비 시뮬레이터"]
_TRIP_DURATION = {"당일치기": 1, "1박 2일": 2, "2박 3일": 3}


def _trip_init_state():
    if not isinstance(st.session_state.get("cart_items"), list):
        st.session_state["cart_items"] = []
    if not isinstance(st.session_state.get("cart_revision"), int):
        st.session_state["cart_revision"] = 0


def _trip_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _trip_token(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def _trip_go(view):
    if view in _TRIP_MENU:
        st.session_state["view"] = view


def _trip_ai_source():
    options = ["관심사로 추천", "장바구니 장소로"]
    value = st.session_state.get("ai_plan_source", st.session_state.get("ai_plan_source_saved", options[0]))
    return value if value in options else options[0]


def _trip_save_ai_source():
    st.session_state["ai_plan_source_saved"] = _trip_ai_source()


def _trip_budget_selected_mode():
    options = ["시간표 예산 계산", "예산으로 새 코스 찾기"]
    value = st.session_state.get("budget_mode", st.session_state.get("budget_mode_saved", options[0]))
    return value if value in options else options[0]


def _trip_save_budget_mode():
    st.session_state["budget_mode_saved"] = _trip_budget_selected_mode()


def _trip_open_budget_builder():
    st.session_state["budget_mode"] = "예산으로 새 코스 찾기"
    st.session_state["budget_mode_saved"] = "예산으로 새 코스 찾기"
    _trip_go("예산 여행 코스")


def _trip_choose_budget(plan):
    st.session_state["active_trip_plan"] = _trip_copy(plan)
    st.session_state["budget_mode"] = "시간표 예산 계산"
    st.session_state["budget_mode_saved"] = "시간표 예산 계산"
    _trip_go("예산 여행 코스")


def _trip_open_cart_ai():
    st.session_state["ai_plan_source"] = "장바구니 장소로"
    st.session_state["ai_plan_source_saved"] = "장바구니 장소로"
    _trip_go("AI 추천")


def _trip_cart_revision():
    st.session_state["cart_revision"] = int(st.session_state.get("cart_revision", 0)) + 1


def _trip_cart_add(row, region=None):
    _trip_init_state()
    place = _cart_normalize_place(row, region)
    if not place:
        st.session_state["cart_notice"] = "장소 이름을 확인할 수 없어 담지 못했어요."
        return
    items = _trip_copy(st.session_state["cart_items"])
    for old in items:
        if old["identity"] == place["identity"]:
            st.session_state["cart_notice"] = f"{place['name']}은 이미 장바구니에 있어요."
            return
    if len(items) >= 60:
        st.session_state["cart_notice"] = "장바구니는 최대 60곳까지 담을 수 있어요. 일부 장소를 정리해 주세요."
        return
    items.append(place)
    st.session_state["cart_items"] = items
    _trip_cart_revision()
    st.session_state["cart_notice"] = f"{place['name']}을 장바구니에 담았어요."


def _trip_cart_remove(identity):
    items = st.session_state.get("cart_items", [])
    updated = [place for place in items if place.get("identity") != identity]
    if len(updated) != len(items):
        st.session_state["cart_items"] = updated
        _trip_cart_revision()


def _trip_cart_move(identity, offset):
    items = list(st.session_state.get("cart_items", []))
    index = next((i for i, place in enumerate(items) if place.get("identity") == identity), None)
    if index is not None and 0 <= index + offset < len(items):
        items[index], items[index + offset] = items[index + offset], items[index]
        st.session_state["cart_items"] = items
        _trip_cart_revision()


def _trip_cart_clear():
    if st.session_state.get("cart_items"):
        st.session_state["cart_items"] = []
        _trip_cart_revision()


def _trip_stamp_plan(plan, region, days, source, settings=None):
    result = _trip_copy(plan)
    result["source"] = source
    result["days"] = int(days)
    if source == "cart":
        names = list(dict.fromkeys(str(p.get("region_label", "")).strip()
                                  for p in result.get("selected_places", []) if p.get("region_label")))
        result["region_label"] = " / ".join(names) or location_text(region)
        result["title"] = "내 장바구니 여행 시간표"
        result["cart_revision"] = int(st.session_state.get("cart_revision", 0))
    else:
        result["region_label"] = location_text(region)
        result["title"] = "관심사로 만든 AI 추천 시간표"
    result["region_context"] = _trip_copy(region)
    result["plan_settings"] = _trip_copy(settings or {})
    digest_data = {key: value for key, value in result.items() if key != "id"}
    result["id"] = hashlib.sha256(json.dumps(digest_data, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]
    return result


def _trip_cart_is_stale(plan):
    return (plan.get("source") == "cart"
            and plan.get("cart_revision") != st.session_state.get("cart_revision", 0))


def _trip_render_nav(view):
    labels = ["🔎 장소 찾기", f"🛒 장바구니 {len(st.session_state.get('cart_items', []))}", "🗓️ AI 추천", "💰 여행 예산"]
    targets = ["콘텐츠 탐색", "장바구니", "AI 추천", "예산 여행 코스"]
    for column, label, target in zip(st.columns(4), labels, targets):
        with column:
            st.button(label, key=f"trip_nav_{target}", type="primary" if view == target else "secondary",
                      on_click=_trip_go, args=(target,), use_container_width=True)
    st.caption("갈 곳을 찾고 → 장바구니에 담고 → 시간표를 만들고 → 필요한 예산을 확인해요.")


def _trip_notice():
    message = st.session_state.pop("cart_notice", None)
    if message:
        st.success(message)


def _trip_csv(rows):
    safe_rows = []
    for row in rows:
        safe = {}
        for key, value in row.items():
            if str(key).startswith("_"):
                continue
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                value = "'" + value
            safe[key] = value
        safe_rows.append(safe)
    return pd.DataFrame(safe_rows).to_csv(index=False).encode("utf-8-sig")


def _trip_render_plan(plan, prefix="trip_plan", show_budget_button=True):
    if plan.get("status") != "ready":
        st.warning(plan.get("message", "시간표를 만들 조건을 확인해 주세요."))
        return
    days = int(plan.get("days", max((row.get("일차", 1) for row in plan.get("itinerary", [])), default=1)))
    st.subheader(plan.get("title", "내 여행 시간표"))
    duration = "당일치기" if days == 1 else f"{days - 1}박 {days}일"
    st.caption(f"{plan.get('region_label', '')} · {duration}")
    if _trip_cart_is_stale(plan):
        st.warning("장바구니가 바뀌었어요. 아래는 변경 전 시간표입니다. 새 장소와 순서를 반영하려면 시간표를 다시 만들어 주세요.")
    if show_budget_button:
        a, b = st.columns(2)
        with a:
            st.button("💰 이 시간표로 예산 계산", key=f"{prefix}_budget", type="primary",
                      use_container_width=True, on_click=_trip_choose_budget, args=(plan,))
        with b:
            st.download_button("📥 시간표 내려받기", _trip_csv(plan.get("itinerary", [])),
                               file_name="villageon_itinerary.csv", mime="text/csv",
                               key=f"{prefix}_download", use_container_width=True)
    lodging = plan.get("lodging")
    if days > 1:
        if lodging:
            st.info(f"🏨 {lodging['name']} · {days - 1}박 동안 같은 숙소를 이용해요.")
        else:
            st.info(f"숙소를 아직 정하지 않았어요. 여행 동안 사용할 공통 숙소 1곳을 정해 주세요. 예산에는 {days - 1}박을 반영해요.")
    unscheduled = plan.get("unscheduled", [])
    if unscheduled:
        st.warning(f"장바구니에서 {len(unscheduled)}곳은 이 시간표에 넣지 못했어요. 아래 목록을 확인하고 기간·체류시간·장소를 조정해 주세요.")
        with st.expander("시간표에 들어가지 않은 장소 확인", expanded=True):
            for item in unscheduled:
                place = item.get("place", item) if isinstance(item, dict) else {}
                name = place.get("name", item.get("name", "장소")) if isinstance(item, dict) else str(item)
                reason = item.get("reason", "시간표 조건을 확인해 주세요.") if isinstance(item, dict) else ""
                st.write(f"• {name} — {reason}")
    st.caption("지도 숫자는 시간표 순서예요. 선은 장소를 직선으로 연결한 개요이며 실제 도로 길찾기는 아닙니다.")
    tabs = st.tabs([f"{day}일차" for day in range(1, days + 1)])
    for day, tab in enumerate(tabs, 1):
        with tab:
            route = _ai_route_day_data(plan, day)
            if not route["stops"]:
                st.info("이 날에 배치된 장소가 없어요. 기간이나 장바구니를 조정해 주세요.")
                continue
            route_map = _ai_route_map(route)
            if route_map is not None:
                st_folium(route_map, height=360, use_container_width=True, returned_objects=[],
                           key=f"{prefix}_map_{plan.get('id', 'plan')}_{day}")
            else:
                st.caption("좌표가 확인된 장소가 없어 이번 일정은 목록으로 보여 드려요.")
            if route["missing"]:
                st.caption("좌표가 없는 일정은 지도에서 제외하고, 그 구간의 연결선은 끊어서 표시해요.")
            for stop in route["stops"]:
                at = str(stop.get("예시 시각", ""))
                end = str(stop.get("예상 종료", ""))
                clock = f"{at}–{end}" if end and end != at else at
                with st.container(border=True):
                    st.markdown(f"**{stop['순서']}. {clock} · {_explore_markdown(stop.get('장소', '직접 선택'))}**")
                    st.caption(f"{stop.get('일정', '')} · {stop.get('분류', '') or '직접 선택'}")
                    if stop.get("주소"):
                        st.text(stop["주소"])
                    note = stop.get("안내")
                    if note:
                        st.caption(note)
                    url = _ai_route_safe_url(stop.get("카카오맵", ""))
                    if url:
                        st.link_button("장소 정보 보기", url, use_container_width=True)
            with st.expander(f"{day}일차 시간표를 표로 보기"):
                frame = pd.DataFrame([{key: value for key, value in row.items()
                                       if not key.startswith("_")} for row in route["stops"]])
                columns = [key for key in ("순서", "예시 시각", "예상 종료", "일정", "장소", "주소", "카카오맵") if key in frame.columns]
                st.dataframe(frame[columns], use_container_width=True, hide_index=True,
                             column_config={"카카오맵": st.column_config.LinkColumn("카카오맵", display_text="장소 확인")})
    warnings = list(dict.fromkeys(str(value) for value in plan.get("warnings", []) if value))
    with st.expander("시간표 계산 기준과 방문 전 확인사항"):
        st.write("시간표는 계획을 돕는 예상 일정이에요. 실제 영업시간·예약 가능 여부·실시간 교통정보는 조회하지 않습니다.")
        st.write("장바구니 시간표의 시작·종료는 여행지에서 보내는 시간입니다. 왕복 이동시간은 별도로 확보하고, 왕복 비용은 예산 화면에서 계산해 주세요.")
        for warning in warnings:
            st.write("• " + warning)


def _trip_default_duration(place):
    category = place.get("main_category") or next(iter(place.get("categories", [])), "관광지")
    return _CART_DEFAULT_MINUTES.get(category, 90)


def _trip_render_cart_builder(region, days, namespace="cart_build"):
    items = st.session_state.get("cart_items", [])
    if not items:
        st.info("콘텐츠 탐색에서 가고 싶은 장소를 먼저 담아 주세요.")
        st.button("🔎 장소 찾으러 가기", on_click=_trip_go, args=("콘텐츠 탐색",),
                  key=f"{namespace}_find", type="primary", use_container_width=True)
        return
    memory = dict(st.session_state.get("cart_settings_memory", {}))
    defaults = {"start": trip_clock_time(9, 0), "end": trip_clock_time(20, 0),
                "order": "가까운 순서", "travel_mode": "대중교통", "lodging_id": ""}
    for field, value in defaults.items():
        key = f"{namespace}_{field}"
        if key not in st.session_state:
            remembered = memory.get(field, value)
            if field in {"start", "end"} and isinstance(remembered, int):
                remembered = trip_clock_time(remembered // 60, remembered % 60)
            st.session_state[key] = remembered
    hotels = [place for place in items if "숙박" in place.get("categories", []) or place.get("main_category") == "숙박"]
    hotel_names = {place["identity"]: place["name"] for place in hotels}
    hotel_ids = list(hotel_names) if hotel_names else [""]
    hotel_key = f"{namespace}_lodging_id"
    if st.session_state[hotel_key] not in hotel_ids:
        st.session_state[hotel_key] = hotel_ids[0]
    st.subheader("담은 장소로 시간표 만들기")
    st.caption("여행 기간은 왼쪽에서 바꿀 수 있어요. 가까운 순서는 첫 장소를 출발점으로 삼는 간단한 추천 순서예요.")
    with st.form(f"{namespace}_form", enter_to_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            start = st.time_input("여행지에서 시작하는 시각", key=f"{namespace}_start", step=900)
            order = st.selectbox("방문 순서", ["가까운 순서", "담은 순서"], key=f"{namespace}_order")
        with c2:
            end = st.time_input("여행지 일정 마치는 시각", key=f"{namespace}_end", step=900)
            travel_mode = st.selectbox("여행지 안 이동수단", ["대중교통", "자가용", "도보"], key=f"{namespace}_travel_mode")
        lodging_id = ""
        if days > 1:
            lodging_id = st.selectbox("여행 내내 머무를 숙소", hotel_ids,
                                      format_func=lambda value: hotel_names.get(value, "숙소는 직접 정할게요"), key=hotel_key)
            if hotels:
                st.caption("담은 숙소 중 한 곳을 고르면 모든 밤과 다음 날 출발에 같은 숙소를 사용해요.")
            else:
                st.caption("장바구니에 숙소가 없어요. 콘텐츠 탐색 → 숙박에서 추가하면 같은 숙소를 일정에 넣을 수 있어요.")
        duration_overrides = {}
        with st.expander("장소별 머무는 시간 조정"):
            for place in items:
                if "숙박" in place.get("categories", []) or place.get("main_category") == "숙박":
                    continue
                identity = place["identity"]
                key = f"{namespace}_stay_{_trip_token(identity)}"
                if key not in st.session_state:
                    st.session_state[key] = int(memory.get("duration_overrides", {}).get(identity, _trip_default_duration(place)))
                duration_overrides[identity] = st.number_input(
                    f"{place['name']} · 머무는 시간 (분)", min_value=15, max_value=240, step=15, key=key)
        submitted = st.form_submit_button("🗓️ 담은 장소로 시간표 만들기", type="primary", use_container_width=True)
    if submitted:
        settings = {"days": int(days), "start_minutes": start.hour * 60 + start.minute,
                    "end_minutes": end.hour * 60 + end.minute, "order": order,
                    "travel_mode": travel_mode, "lodging_id": lodging_id,
                    "duration_overrides": duration_overrides}
        st.session_state["cart_settings_memory"] = {**settings, "start": settings["start_minutes"], "end": settings["end_minutes"]}
        plan = _cart_build_plan(items, settings)
        if plan.get("status") == "ready":
            stamped = _trip_stamp_plan(plan, region, days, "cart", settings)
            st.session_state["cart_plan"] = stamped
            st.session_state["active_trip_plan"] = _trip_copy(stamped)
            st.success("담은 장소로 시간표를 만들었어요. 아래에서 지도와 예산 계산을 확인해 보세요.")
        else:
            st.error(plan.get("message", "입력 조건을 확인해 주세요."))
            if plan.get("unscheduled"):
                with st.expander("시간표에 넣지 못한 장소와 이유", expanded=True):
                    for place in plan["unscheduled"]:
                        st.write(f"• {place.get('name', '장소')} — {place.get('reason', '시간표 조건을 조정해 주세요.')}")
            st.session_state.pop("cart_plan", None)
    plan = st.session_state.get("cart_plan")
    if plan:
        if int(plan.get("days", days)) != int(days):
            st.warning("여행 기간이 바뀌었어요. 아래는 이전 기간의 시간표이니 새 기간으로 다시 만들어 주세요.")
        _trip_render_plan(plan, prefix=namespace)


def _trip_render_cart_storage():
    with st.expander("장바구니 저장 · 불러오기 · 비우기"):
        st.caption("장바구니는 현재 접속 중에 유지돼요. 새로고침이나 접속 종료로 초기화될 수 있으니 필요하면 파일로 보관해 주세요.")
        payload = {"version": 1, "places": st.session_state.get("cart_items", [])}
        st.download_button("장바구니 파일 저장", json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name="villageon_cart.json", mime="application/json", key="cart_backup", use_container_width=True)
        upload = st.file_uploader("저장한 장바구니 파일", type=["json"], key="cart_import_file")
        if st.button("파일의 장소를 장바구니에 추가", key="cart_import_submit", disabled=upload is None, use_container_width=True):
            try:
                if upload.size > 1_000_000:
                    raise ValueError("장바구니 파일은 1MB 이하만 불러올 수 있어요.")
                data = json.loads(upload.getvalue().decode("utf-8-sig"))
                records = data.get("places") if isinstance(data, dict) and data.get("version") == 1 else None
                if not isinstance(records, list) or len(records) > 60:
                    raise ValueError("VillageON에서 저장한 60곳 이하의 장바구니 파일을 선택해 주세요.")
                normalized = []
                for row in records:
                    place = _cart_normalize_place(row)
                    if place:
                        normalized.append(place)
                if not normalized:
                    raise ValueError("불러올 수 있는 장소가 없어요.")
                before = len(st.session_state.get("cart_items", []))
                for place in normalized:
                    _trip_cart_add(place)
                added = len(st.session_state["cart_items"]) - before
                st.session_state["cart_notice"] = f"장바구니에 {added}곳을 추가했어요. 중복 장소와 최대 60곳을 넘는 항목은 추가하지 않았어요."
                st.rerun()
            except (ValueError, TypeError, UnicodeDecodeError, RecursionError) as exc:
                st.error(str(exc) if isinstance(exc, ValueError) else "장바구니 파일을 읽을 수 없어요. 저장한 JSON 파일인지 확인해 주세요.")
        with st.form("cart_clear_form"):
            checked = st.checkbox("장바구니의 장소를 모두 지울게요", key="cart_clear_confirm")
            clear = st.form_submit_button("장바구니 비우기", use_container_width=True)
        if clear:
            if checked:
                _trip_cart_clear()
                st.rerun()
            else:
                st.info("전체 삭제를 원하면 확인란을 선택해 주세요.")


def render_cart(region, days):
    st.title("🛒 내 여행 장바구니")
    st.caption("여러 검색에서 담은 장소를 한곳에 모았어요. 방문 순서를 정하고 나만의 시간표를 만들어 보세요.")
    _trip_notice()
    items = st.session_state.get("cart_items", [])
    c1, c2 = st.columns(2)
    with c1:
        st.button("➕ 장소 더 담기", key="cart_find_more", on_click=_trip_go, args=("콘텐츠 탐색",), use_container_width=True)
    with c2:
        st.button("🗓️ AI 추천에서 이어서 만들기", key="cart_open_ai", on_click=_trip_open_cart_ai, use_container_width=True)
    if items:
        st.subheader(f"가고 싶은 곳 {len(items)}곳")
        st.caption("위·아래 버튼으로 담은 순서를 바꿀 수 있어요. 시간표에서 ‘담은 순서’를 선택하면 반영됩니다.")
        for index, place in enumerate(items):
            identity = place["identity"]
            token = _trip_token(identity)
            with st.container(border=True):
                st.markdown(f"**{index + 1}. {_explore_markdown(place['name'])}**")
                st.caption(" · ".join(place.get("categories", [])))
                if place.get("address"):
                    st.text(place["address"])
                if not _ai_route_coordinates(place.get("lat"), place.get("lon")):
                    st.caption("좌표 정보 없음 · 시간표에는 포함할 수 있지만 지도에는 표시되지 않아요.")
                up, down, remove = st.columns(3)
                up.button("↑ 위로", key=f"cart_up_{token}", on_click=_trip_cart_move, args=(identity, -1), disabled=index == 0, use_container_width=True)
                down.button("↓ 아래로", key=f"cart_down_{token}", on_click=_trip_cart_move, args=(identity, 1), disabled=index == len(items) - 1, use_container_width=True)
                remove.button("삭제", key=f"cart_remove_{token}", on_click=_trip_cart_remove, args=(identity,), use_container_width=True)
    else:
        st.info("아직 담은 장소가 없어요. 콘텐츠 탐색에서 ‘장바구니에 담기’를 눌러 주세요.")
    _trip_render_cart_storage()
    _trip_render_cart_builder(region, days)


def render_ai(region, analysis, local_data, interests, days):
    st.title("🗓️ AI 여행 시간표")
    st.caption("관심사로 추천받거나, 장바구니에 담은 장소로 여행을 계획해 보세요.")
    if "ai_plan_source" not in st.session_state:
        st.session_state["ai_plan_source"] = _trip_ai_source()
    source = st.radio("어떤 장소로 계획할까요?", ["관심사로 추천", "장바구니 장소로"],
                      key="ai_plan_source", horizontal=True, on_change=_trip_save_ai_source)
    if source == "장바구니 장소로":
        st.button(f"🛒 장바구니 {len(st.session_state.get('cart_items', []))}곳 편집", key="ai_edit_cart",
                  on_click=_trip_go, args=("장바구니",), use_container_width=True)
        _trip_render_cart_builder(region, days, namespace="ai_cart_build")
        return
    persisted = _ai_normalize_interests(st.session_state.get("travel_interests", interests))
    st.session_state["travel_interests"] = persisted
    if "ai_travel_interests" not in st.session_state:
        st.session_state["ai_travel_interests"] = list(persisted)
    selected = st.multiselect("여행 관심사", _AI_INTEREST_OPTIONS, key="ai_travel_interests",
                              format_func=_ai_interest_label, on_change=_ai_store_interests)
    st.caption("실제로 검색된 장소를 선택한 관심사 규칙에 맞춰 추천해요. 관심사를 바꾸면 시간표도 다시 구성됩니다.")
    with st.expander("추천 후보 장소 · 카카오 정확도순 검색 결과"):
        candidate_state = _ai_candidate_render(local_data, selected)
    plan = _ai_build_itinerary(local_data, selected, days)
    if plan.get("status") != "ready":
        if plan.get("status") == "no_matches" and candidate_state.get("unresolved"):
            st.warning("일부 장소 데이터를 확인하지 못했어요. 추천 후보 조회 안내를 확인하거나 장바구니의 장소를 이용해 주세요.")
        else:
            st.info(plan.get("message", "관심사와 지역을 선택해 주세요."))
        return
    stamped = _trip_stamp_plan(plan, region, days, "ai")
    st.session_state["ai_plan"] = stamped
    st.session_state["active_trip_plan"] = _trip_copy(stamped)
    st.caption("시간표 시각은 예시예요. 아래 ‘이 시간표로 예산 계산’을 누르면 같은 일정의 왕복 교통·식사·카페·숙박 비용을 계산해요.")
    _trip_render_plan(stamped, prefix="ai_plan")


def render_budget_trip(region, local_data, interests, days, api_key):
    if "budget_mode" not in st.session_state:
        st.session_state["budget_mode"] = _trip_budget_selected_mode()
    mode = st.radio("여행 예산 계산 방법", ["시간표 예산 계산", "예산으로 새 코스 찾기"],
                    key="budget_mode", horizontal=True, on_change=_trip_save_budget_mode)
    if mode == "예산으로 새 코스 찾기":
        _render_budget_builder_legacy(region, local_data, interests, days, api_key)
        return
    st.title("💰 내 시간표의 여행 예산")
    st.caption("이미 만든 시간표를 그대로 사용해요. 출발지에서 오가는 왕복비와 여행지 안의 지출을 함께 계산합니다.")
    plan = st.session_state.get("active_trip_plan")
    if not plan or plan.get("status") != "ready":
        st.info("먼저 장바구니 또는 AI 추천에서 시간표를 만들어 주세요.")
        a, b = st.columns(2)
        a.button("🛒 장바구니로 시간표 만들기", key="budget_empty_cart", on_click=_trip_go, args=("장바구니",), use_container_width=True)
        b.button("🗓️ AI 추천 받기", key="budget_empty_ai", on_click=_trip_go, args=("AI 추천",), type="primary", use_container_width=True)
        st.button("예산부터 정하고 새 코스 찾기", key="budget_empty_builder", on_click=_trip_open_budget_builder, use_container_width=True)
        return
    available = {"cart": st.session_state.get("cart_plan"), "ai": st.session_state.get("ai_plan")}
    other = "ai" if plan.get("source") == "cart" else "cart"
    if available.get(other) and available[other].get("status") == "ready":
        label = "관심사 추천 시간표로 바꾸기" if other == "ai" else "장바구니 시간표로 바꾸기"
        st.button(label, key="budget_switch_plan", on_click=_trip_choose_budget, args=(available[other],), use_container_width=True)
    if _trip_cart_is_stale(plan):
        st.warning("장바구니가 바뀐 뒤 시간표를 다시 만들지 않았어요. 아래 계산은 저장된 이전 시간표 기준입니다.")
        st.button("장바구니에서 시간표 다시 만들기", key="budget_stale_cart", on_click=_trip_go, args=("장바구니",), use_container_width=True)
    actual_days = int(plan.get("days", days))
    st.info(f"계산할 시간표: {plan.get('title', '여행 시간표')} · {actual_days}일 · {plan.get('region_label', '')}")
    if actual_days != int(days) or plan.get("region_label") != location_text(region):
        st.caption("계산에는 이 저장된 시간표의 지역·기간을 사용해요. 왼쪽 선택만 바꿔도 저장된 시간표가 바뀌지는 않습니다.")
    render_plan_budget(plan, plan.get("region_context", region), api_key, namespace="schedule_cost")
    with st.expander("예산에 사용한 시간표 · 지도 확인"):
        _trip_render_plan(plan, prefix="budget_snapshot", show_budget_button=False)


def _trip_extra_css():
    st.markdown("""
<style>
[data-testid="stMainBlockContainer"] {max-width:1200px;padding-top:1.5rem;}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:#d5e4dc;border-radius:16px;}
[data-testid="stMain"] [data-testid="stForm"] {background:#ffffff;border:1px solid #d5e4dc;border-radius:16px;}
[data-testid="stMain"] [data-testid="stExpander"] {background:#ffffff;border-radius:12px;}
[data-testid="stTabs"] [role="tab"] {min-height:52px;font-size:17px;padding:10px 20px;}
[data-testid="stMain"] h1 {font-size:2rem;line-height:1.35;}
[data-testid="stMain"] h2 {font-size:1.45rem;}
@media(max-width:640px){
  [data-testid="stMainBlockContainer"]{padding:1rem;}
  [data-testid="stMain"] h1{font-size:1.65rem;}
  [data-testid="stTabs"] [role="tab"]{padding:10px 14px;}
}
</style>
""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
