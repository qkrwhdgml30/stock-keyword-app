import os
import io
import time
import streamlit as st
from PIL import Image
from google import genai
import gspread
import pandas as pd

# --- 기본 금지 키워드 초기값 설정 ---
DEFAULT_FORBIDDEN = [
    "감성일러스트", "다이어리요소", "디자인소스", "그래픽소스", "그래픽요소", 
    "포인트일러스트", "ppt요소", "카드뉴스요소", "아이콘", "라인아이콘", "디자인재료",
    "벡터", "누끼", "투명배경", "마켓팅용아님", "감성적인표현제외"
]

if "forbidden_list" not in st.session_state:
    st.session_state.forbidden_list = DEFAULT_FORBIDDEN.copy()

st.set_page_config(page_title="스톡 키워드 자동 추출 & 실시간 동기화", layout="wide")

# --- UI 스타일 추가 (보관함 썸네일 카드 크기 고정) ---
st.markdown("""
    <style>
    .stImage img {
        height: 180px !important;
        object-fit: cover !important;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎨 스톡 이미지 키워드 자동 추출 & 구글 시트 영구 연동")
st.caption("썸네일 사이즈 통일 + 503 서버 안정성 패치 + PC/아이패드 실시간 동기화 적용 완료")

# --- 구글 스프레드시트 연결 함수 ---
def get_google_sheet():
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sheet_url = st.secrets["SHEET_URL"]
        sheet = gc.open_by_url(sheet_url).sheet1
        return sheet
    except Exception:
        return None

# --- 구글 시트에서 보관함 데이터 불러오기 ---
def load_gallery_from_sheet():
    sheet = get_google_sheet()
    if not sheet:
        return []
    try:
        data = sheet.get_all_records()
        gallery = []
        for row in data:
            gallery.append({
                "name": row.get("작품명", ""),
                "miricanvas": row.get("미리캔버스용", ""),
                "crowdpic": row.get("크라우드픽용", ""),
                "url": row.get("작품이미지", "")
            })
        return gallery
    except Exception:
        return []

# --- 구글 시트에 새 작업물 저장하기 ---
def save_to_google_sheet(name, m_kw, c_kw, img_url=""):
    sheet = get_google_sheet()
    if sheet:
        try:
            sheet.append_row([img_url, name, m_kw, c_kw])
        except Exception:
            pass

# --- 사이드바: 금지 키워드 관리 ---
st.sidebar.header("⚙️ 금지 키워드 관리")
st.sidebar.caption("필터링할 단어를 추가하거나 삭제할 수 있습니다.")

new_forbidden = st.sidebar.text_input("추가할 금지 키워드 입력")
if st.sidebar.button("➕ 금지어 추가"):
    if new_forbidden and new_forbidden.strip() not in st.session_state.forbidden_list:
        st.session_state.forbidden_list.append(new_forbidden.strip())
        st.sidebar.success(f"'{new_forbidden.strip()}' 추가 완료!")
        st.rerun()

with st.sidebar.expander("📋 현재 금지 키워드 목록 관리", expanded=True):
    to_remove = []
    for kw in st.session_state.forbidden_list:
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            st.write(f"- {kw}")
        with col2:
            if st.button("❌", key=f"del_{kw}", help=f"'{kw}' 삭제"):
                to_remove.append(kw)
                
    if to_remove:
        for kw in to_remove:
            st.session_state.forbidden_list.remove(kw)
        st.rerun()

# --- 이미지 압축 함수 (용량 축소 및 화질 최적화) ---
def optimize_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buffer, format="JPEG", quality=75)
    return buffer.getvalue()

# --- Gemini 단건 분석 함수 (503 서버 과부하 자동 재시도 로직 포함) ---
def analyze_single_image(file_name, image_bytes, api_key, forbidden_words):
    optimized_bytes = optimize_image(image_bytes)
    client = genai.Client(api_key=api_key)
    image = Image.open(io.BytesIO(optimized_bytes))
    
    prompt = f"""
    이 이미지의 시각적 요소, 객체, 상황, 인물, 색상, 분위기 등 '요소 본연의 핵심 키워드'만 한국어로 추출해줘.
    1. 첫 번째 줄에는 미리캔버스용 핵심 키워드를 쉼표(,)로 구분하여 정확히 25개 적어줘.
    2. 두 번째 줄에는 크라우드픽용 핵심 키워드를 쉼표(,)로 구분하여 정확히 40개 적어줘.
    다른 설명이나 번호는 절대 붙이지 말고 오직 아래 두 줄 형식으로만 출력해줘:
    미리캔버스: [키워드들...]
    크라우드픽: [키워드들...]

    [절대 포함하지 말아야 할 금지 키워드 리스트]:
    {', '.join(forbidden_words)}
    위 금지 단어들과 유사한 포괄적/제작방식/마케팅성 단어는 반드시 완전히 제외해줘.
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=[image, prompt]
            )
            
            text_res = response.text.strip()
            m_kw_str, c_kw_str = "", ""
            
            for line in text_res.split("\n"):
                if "미리캔버스:" in line:
                    m_kw_str = line.replace("미리캔버스:", "").strip()
                elif "크라우드픽:" in line:
                    c_kw_str = line.replace("크라우드픽:", "").strip()
                    
            def filter_text(k_str):
                k_list = [k.strip() for k in k_str.replace("\n", "").split(",") if k.strip()]
                filtered = [k for k in k_list if not any(f in k for f in forbidden_words)]
                return ", ".join(filtered)

            return {
                "name": file_name,
                "bytes": optimized_bytes,
                "miricanvas": filter_text(m_kw_str) if m_kw_str else filter_text(text_res),
                "
