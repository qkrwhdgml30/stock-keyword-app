import os
import io
import time
import streamlit as st
from PIL import Image
from google import genai
import gspread
import pandas as pd

DEFAULT_FORBIDDEN = [
    "감성일러스트", "다이어리요소", "디자인소스", "그래픽소스", "그래픽요소", 
    "포인트일러스트", "ppt요소", "카드뉴스요소", "아이콘", "라인아이콘", "디자인재료",
    "벡터", "누끼", "투명배경", "마켓팅용아님", "감성적인표현제외"
]

if "forbidden_list" not in st.session_state:
    st.session_state.forbidden_list = DEFAULT_FORBIDDEN.copy()

st.set_page_config(page_title="스톡 키워드 자동 추출 & 실시간 동기화", layout="wide")

st.markdown(
    "<style>.stImage img { height: 180px !important; object-fit: cover !important; border-radius: 8px; }</style>",
    unsafe_allow_html=True
)

st.title("🎨 스톡 이미지 키워드 자동 추출 & 구글 시트 영구 연동")
st.caption("썸네일 사이즈 통일 + 503 서버 안정성 패치 + PC/아이패드 실시간 동기화 적용 완료")

def get_google_sheet():
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sheet_url = st.secrets["SHEET_URL"]
        sheet = gc.open_by_url(sheet_url).sheet1
        return sheet
    except Exception:
        return None

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

def save_to_google_sheet(name, m_kw, c_kw, img_url=""):
    sheet = get_google_sheet()
    if sheet:
        try:
            sheet.append_row([img_url, name, m_kw, c_kw])
        except Exception:
            pass

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

def optimize_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buffer, format="JPEG", quality=75)
    return buffer.getvalue()

def analyze_single_image(file_name, image_bytes, api_key, forbidden_words):
    optimized_bytes = optimize_image(image_bytes)
    client = genai.Client(api_key=api_key)
    image = Image.open(io.BytesIO(optimized_bytes))
    
    forbid_str = ", ".join(forbidden_words)
    prompt = (
        "이 이미지의 시각적 요소, 객체, 상황, 인물, 색상, 분위기 등 요소 본연의 핵심 키워드만 한국어로 추출해줘. "
        "1. 첫 번째 줄에는 미리캔버스용 핵심 키워드를 쉼표로 구분하여 정확히 25개 적어줘. "
        "2. 두 번째 줄에는 크라우드픽용 핵심 키워드를 쉼표로 구분하여 정확히 40개 적어줘. "
        "다른 설명이나 번호는 절대 붙이지 말고 오직 아래 두 줄 형식으로만 출력해줘: "
        "미리캔버스: [키워드들...] "
        "크라우드픽: [키워드들...] "
        f"[절대 포함하지 말아야 할 금지 키워드 리스트]: {forbid_str}. "
        "위 금지 단어들과 유사한 포괄적/제작방식/마케팅성 단어는 반드시 완전히 제외해줘."
    )

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
                "crowdpic": filter_text(c_kw_str) if c_kw_str else filter_text(text_res)
            }
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if attempt < max_retries - 1:
                    time.sleep(3.0)
                    continue
            return {"name": file_name, "error": str(e)}

tab1, tab2 = st.tabs(["📤 대량 이미지 업로드 및 추출", "🖼️ 작업물 보관함 (사이즈 통일)"])

with tab1:
    st.subheader("아이패드 / PC 파일 대량 업로드 (순차 안전 처리)")
    
    uploaded_files = st.file_uploader(
        "일러스트/요소 이미지들을 여러 장 선택해 주세요 (PNG, JPG)", 
        type=["png", "jpg", "jpeg"], 
        accept_multiple_files=True
    )

    if uploaded_files:
        st.info(f"📁 총 {len(uploaded_files)}개의 파일이 선택되었습니다. (화질 최적화 및 순차 처리)")
        
        if st.button("✨ 키워드 자동 추출 및 시트 저장", type="primary"):
            try:
                gemini_api_key = st.secrets["GEMINI_API_KEY"]
            except Exception:
                gemini_api_key = None
                
            if not gemini_api_key:
                st.error("⚠️ Streamlit Secrets에 GEMINI_API_KEY가 설정되어 있지 않습니다.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                current_forbidden = st.session_state.forbidden_list
                
                results_container = []
                
                for idx, file in enumerate(uploaded_files):
                    status_text.text(f"진행 중 ({idx+1}/{len(uploaded_files)}): {file.name} 분석 중...")
                    
                    res = analyze_single_image(file.name, file.getvalue(), gemini_api_key, current_forbidden)
                    results_container.append(res)
                    
                    if "error" not in res:
                        save_to_google_sheet(res["name"], res["miricanvas"], res["crowdpic"])
                    
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                    
                    if idx < len(uploaded_files) - 1:
                        time.sleep(2.0)
                
                status_text.text("✅ 모든 이미지 분석 및 구글 시트 저장 완료!")
                st.success("결과가 보관함에 영구 저장되었습니다.")
                
                for item in results_container:
                    if "error" in item:
                        st.error(f"📁 '{item['name']}' 처리 실패: {item['error']}")
                    else:
                        with st.expander(f"📁 파일명: {item['name']}", expanded=True):
                            col_img, col_txt = st.columns([1, 2])
                            with col_img:
                                st.image(item["bytes"], use_container_width=True)
                            with col_txt:
                                st.markdown("**🎨 미리캔버스용 (25개)**")
                                st.text_area("미리캔버스 복사 영역", value=item["miricanvas"], height=80, key=f"m_{item['name']}")
                                st.markdown("**☁️ 크라우드픽용 (40개)**")
                                st.text_area("크라우드픽 복사 영역", value=item["crowdpic"], height=100, key=f"c_{item['name']}")

with tab2:
    st.subheader("전체 작업물 보관함 (사이즈 통일 갤러리)")
    st.caption("모든 이미지 카드의 높이와 비율이 일정하게 통일되어 보기 편하도록 정렬됩니다.")
    
    sheet_data = load_gallery_from_sheet()
    
    if not sheet_data:
        st.write("아직 구글 시트에 저장된 작업물이 없습니다.")
    else:
        cols = st.columns(3)
        for idx, item in enumerate(sheet_data):
            col = cols[idx % 3]
            with col:
                st.caption(f"📁 {item['name']}")
                if item["url"]:
                    st.image(item["url"], use_container_width=True)
                
                with st.expander("🔍 키워드 보기"):
                    st.markdown("**[미리캔버스용]**")
                    st.code(item["miricanvas"], language="text")
                    st.markdown("**[크라우드픽용]**")
                    st.code(item["crowdpic"], language="text")
