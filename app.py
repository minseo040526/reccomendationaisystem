import streamlit as st
import pandas as pd
import random
import re
import time

# --- 데이터 로드 및 전처리 ---
@st.cache_data
def load_data(file_path):
    """메뉴 데이터 로드 및 전처리"""
    try:
        # 파일명 수정: 'menu.csv' 사용
        df = pd.read_csv(file_path)
        # 태그를 리스트 형태로 변환
        df['tags_list'] = df['tags'].apply(lambda x: [re.sub(r'#', '', tag).strip() for tag in x.split(',')])
        return df
    except FileNotFoundError:
        st.error(f"⚠️ 에러: {file_path} 파일을 찾을 수 없습니다. 파일을 확인해주세요.")
        return pd.DataFrame()

# 파일명: menu.csv
menu_df = load_data('menu.csv')

# 사용 가능한 모든 태그 추출
all_tags = sorted(list(set(tag for sublist in menu_df['tags_list'].dropna() for tag in sublist)))

# --- 세션 상태 초기화 ---
if 'user_db' not in st.session_state:
    # {전화번호: {'coupons': int, 'visits': int, 'orders': list}}
    st.session_state['user_db'] = {}
if 'phone_number' not in st.session_state:
    st.session_state['phone_number'] = None
if 'page' not in st.session_state:
    st.session_state['page'] = 'home'
if 'recommendations' not in st.session_state:
    st.session_state['recommendations'] = []

# --- 페이지 이동 함수 ---
def set_page(page_name):
    st.session_state['page'] = page_name

# --- 컴포넌트 함수 ---
def show_status_sidebar():
    """현재 사용자 상태(쿠폰, 방문, 이력 버튼) 표시"""
    phone = st.session_state['phone_number']
    if phone and phone in st.session_state['user_db']:
        user_data = st.session_state['user_db'][phone]
        coupons = user_data['coupons']
        visits = user_data['visits']
        
        st.sidebar.title("나의 정보")
        st.sidebar.info(f"방문 횟수: **{visits}회**")
        st.sidebar.markdown(f"**🎫 쿠폰함**")
        st.sidebar.success(f"사용 가능 쿠폰: **{coupons}개**")
        
        # 과거 주문 이력 확인 버튼
        if st.sidebar.button("🔍 과거 주문 이력 확인"):
            set_page('order_history')
            st.rerun()

def use_coupon_toggle():
    """쿠폰 사용 여부 체크박스 및 적용 로직"""
    phone = st.session_state['phone_number']
    if phone and st.session_state['user_db'][phone]['coupons'] > 0:
        st.session_state['use_coupon'] = st.checkbox(
            '🎫 쿠폰 1개 사용 (총 주문 금액 1,000원 할인)',
            value=st.session_state.get('use_coupon', False)
        )
    else:
        st.session_state['use_coupon'] = False
        st.markdown("<p style='color:gray;'>사용 가능한 쿠폰이 없습니다.</p>", unsafe_allow_html=True)

# --- 메뉴 추천 로직 (당도 필터링 추가) ---
def recommend_menus(df, budget, selected_tags, sweetness_level, recommendation_count=3):
    """예산, 태그, 당도를 고려한 메뉴 조합 추천"""

    # 1. 태그 필터링 (선택된 태그를 하나라도 포함)
    if selected_tags:
        filtered_df = df[df['tags_list'].apply(lambda x: any(tag in selected_tags for tag in x))]
    else:
        filtered_df = df
        
    if filtered_df.empty:
        return []

    # 2. 당도 필터링 점수 부여 (당도 레벨과의 차이가 작을수록 선호)
    filtered_df = filtered_df.copy()
    filtered_df['sweetness_diff'] = abs(filtered_df['sweetness'] - sweetness_level)
    
    # 3. 메뉴 카테고리 분리
    # 음료/베이커리/기타(식사) 분리 추천 요구사항을 위해 카테고리를 나누지만,
    # 예산 내 조합은 메인 + 베이커리/디저트 중심으로 구현
    
    # **음료와 베이커리는 따로 추천합니다. 조합 추천은 '식사 + 베이커리' 세트 조합입니다.**
    
    drink_df = filtered_df[filtered_df['category'].isin(['커피', '음료', '티'])].sort_values(by='sweetness_diff')
    bakery_df = filtered_df[filtered_df['category'].isin(['빵', '디저트'])].sort_values(by='sweetness_diff')
    main_menu_df = filtered_df[filtered_df['category'].isin(['샌드위치', '샐러드'])].sort_values(by='sweetness_diff')

    recommendations = []
    
    # 음료 및 베이커리 단품 추천
    rec_drink = drink_df.iloc[0] if not drink_df.empty else None
    rec_bakery = bakery_df.iloc[0] if not bakery_df.empty else None

    # 세트 조합 추천 (메인 + 베이커리)
    attempts = 0
    while len(recommendations) < recommendation_count and attempts < 100:
        attempts += 1
        
        # 당도 차이가 작은 메뉴를 우선적으로 샘플링하기 위해, 상위 30% 내에서 선택
        current_main_df = main_menu_df.head(max(1, len(main_menu_df) // 3))
        current_bakery_df = bakery_df.head(max(1, len(bakery_df) // 3))
        
        if current_main_df.empty or current_bakery_df.empty:
            break

        # 무작위로 메인 메뉴와 베이커리 메뉴 선택
        main_item = current_main_df.sample(1).iloc[0]
        bakery_item = current_bakery_df.sample(1).iloc[0]
        
        total_price = main_item['price'] + bakery_item['price']
        
        if total_price <= budget:
            combo_main_bakery = f"**메인**: {main_item['name']} | **베이커리/디저트**: {bakery_item['name']}"
            combo_price = total_price
            
            # 중복 방지
            if combo_main_bakery not in [rec.split('(')[0].strip() for rec in recommendations]:
                recommendations.append(f"{combo_main_bakery} (총 {combo_price}원)")

    # 조합이 부족할 경우, 가장 비싼 단품 메뉴 추가
    if len(recommendations) < recommendation_count:
        single_items = filtered_df[filtered_df['price'] <= budget].sort_values(by=['sweetness_diff', 'price'], ascending=[True, False])
        for _, row in single_items.head(recommendation_count - len(recommendations)).iterrows():
            combo = f"**단품**: {row['name']}"
            if combo not in [rec.split('(')[0].strip() for rec in recommendations]:
                recommendations.append(f"{combo} (총 {row['price']}원)")
                
    # 음료/베이커리 별도 추천 메시지 추가
    drink_msg = f"**음료 추천**: {rec_drink['name']} ({rec_drink['price']}원, 당도 {rec_drink['sweetness']})" if rec_drink else "☕ 적합한 음료를 찾지 못했습니다."
    bakery_msg = f"**베이커리 단품 추천**: {rec_bakery['name']} ({rec_bakery['price']}원, 당도 {rec_bakery['sweetness']})" if rec_bakery else "🍰 적합한 베이커리를 찾지 못했습니다."
    
    st.info(drink_msg)
    st.info(bakery_msg)
            
    return recommendations


# --- 페이지: 홈 (전화번호 입력) ---
def home_page():
    st.title("🍓 루시베이커리 메뉴 추천 서비스")
    
    st.subheader("👋 환영합니다! 전화번호를 입력해주세요.")
    
    phone_input = st.text_input(
        "📱 휴대폰 번호 (예: 01012345678)", 
        max_chars=11, 
        key='phone_input_key'
    )
    
    if st.button("시작하기"):
        if re.match(r'^\d{10,11}$', phone_input):
            st.session_state['phone_number'] = phone_input
            
            # DB 조회 또는 신규 등록 (orders 리스트 추가)
            if phone_input not in st.session_state['user_db']:
                st.session_state['user_db'][phone_input] = {'coupons': 0, 'visits': 1, 'orders': []}
                st.success(f"🎉 신규 고객님으로 등록되었습니다! 첫 방문 쿠폰 1개가 지급됩니다.")
                st.session_state['user_db'][phone_input]['coupons'] += 1 # 1회 방문 쿠폰 즉시 지급
            else:
                st.session_state['user_db'][phone_input]['visits'] += 1
                visits = st.session_state['user_db'][phone_input]['visits']
                st.info(f"✨ {phone_input} 고객님, 다시 오셨네요! 총 방문 횟수: {visits}회")
            
            set_page('recommend')
            st.rerun()
        else:
            st.error("유효하지 않은 전화번호 형식입니다. '-' 없이 10~11자리 숫자를 입력해주세요.")

# --- 페이지: 메뉴 추천 설정 ---
def recommend_page():
    st.title("🤖 AI 맞춤 메뉴 추천")
    
    show_status_sidebar()
    
    st.subheader("1. 예산 설정 및 쿠폰 사용")
    
    budget = st.slider(
        "💰 최대 예산 설정 (원)",
        min_value=5000, max_value=30000, step=1000, value=15000
    )
    
    use_coupon_toggle()
    
    final_budget = budget
    if st.session_state.get('use_coupon'):
        coupon_discount = 1000 
        final_budget = budget + coupon_discount 
        st.info(f"쿠폰 사용으로 인해 **{coupon_discount}원** 할인 적용! 추천은 최대 {final_budget}원 기준으로 진행됩니다.")
        
    st.subheader("2. 선호 해시태그 및 당도 선택")
    
    # 당도 슬라이더 (추가됨)
    sweetness_level = st.slider(
        "🍰 원하는 당도 수준 (0: 담백 ~ 5: 매우 달콤)",
        min_value=0, max_value=5, step=1, value=3, key='sweetness_slider'
    )
    st.session_state['sweetness_level'] = sweetness_level
    
    # 해시태그 멀티셀렉트
    selected_tags = st.multiselect(
        "🏷️ 원하는 메뉴 스타일을 선택하세요 (최대 3개):",
        options=all_tags, max_selections=3,
        default=st.session_state.get('selected_tags', [])
    )
    st.session_state['selected_tags'] = selected_tags
    
    # 메뉴판 보러가기 탭 (추가됨)
    if st.button("메뉴판 보러가기 ➡️"):
        set_page('menu_board')
        st.rerun()

    # 추천 버튼
    if st.button("메뉴 추천 받기", type="primary"):
        st.session_state['recommendations'] = recommend_menus(menu_df, final_budget, selected_tags, sweetness_level, recommendation_count=3)
        st.session_state['recommended'] = True
        st.session_state['selected_set'] = None # 선택 초기화
        st.rerun()

    # 추천 결과 표시
    if st.session_state.get('recommended') and st.session_state['recommendations']:
        st.markdown("---")
        st.subheader("✨ 추천 결과 (세트)")
        
        options = {}
        for i, rec in enumerate(st.session_state['recommendations']):
            options[f"세트 {i+1} ({rec.split('(총 ')[1].split('원)')[0]}원)"] = rec
        
        # 세트 선택 라디오 버튼 (추가됨)
        selected_key = st.radio(
            "✅ 주문할 추천 세트 하나를 선택하세요:",
            options=list(options.keys()),
            key='set_selection'
        )
        st.session_state['selected_set'] = options[selected_key]

        # 주문 완료 버튼
        st.markdown("---")
        if st.button("🛒 선택한 세트로 주문 완료 및 쿠폰 발급"):
            set_page('order_complete')
            st.rerun()
    elif st.session_state.get('recommended'):
        st.error("😭 선택하신 조건으로 추천 가능한 메뉴 조합이 없습니다. 예산 또는 조건을 조정해주세요.")

# --- 페이지: 주문 완료 ---
def order_complete_page():
    st.title("✅ 주문 완료")
    st.balloons()
    
    phone = st.session_state['phone_number']
    
    # 1. 주문 번호 생성 및 표시 (추가됨)
    order_id = int(time.time() * 1000) % 1000000 # 간단한 6자리 주문번호
    st.header(f"주문 번호: **{order_id}**")
    
    selected_menu = st.session_state['selected_set']
    
    # 2. 주문 내역 저장 (추가됨)
    order_data = {
        'order_id': order_id,
        'items': selected_menu,
        'date': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    if phone in st.session_state['user_db']:
        st.session_state['user_db'][phone]['orders'].append(order_data)
        visits = st.session_state['user_db'][phone]['visits']
        
        st.markdown("---")
        st.subheader("🧾 주문 내역")
        st.success(f"**선택 메뉴**: {selected_menu}")
        
        # 3. 쿠폰 사용 처리
        if st.session_state.get('use_coupon'):
            st.session_state['user_db'][phone]['coupons'] -= 1
            st.warning("🎫 쿠폰 1개가 사용되었습니다.")
            st.session_state['use_coupon'] = False
        
        # 4. 쿠폰 발급 (1, 5, 10회 방문 시 증정)
        # 1회 방문은 홈 페이지에서 이미 지급되었으므로 5회, 10회만 추가 체크
        if visits in [5, 10]:
            st.session_state['user_db'][phone]['coupons'] += 1
            st.success(f"🎁 {visits}회 방문 기념 쿠폰 1개가 발급되어 쿠폰함에 저장되었습니다!")
        elif visits not in [1, 5, 10]:
            st.info("다음 쿠폰 증정은 5회, 10회 방문 시에 이루어집니다.")
            
        st.info(f"현재 사용 가능 쿠폰: **{st.session_state['user_db'][phone]['coupons']}개**")
        
    st.markdown("---")
    if st.button("🏠 처음으로 돌아가기"):
        # 상태 초기화
        st.session_state['phone_number'] = None
        st.session_state['recommended'] = False
        st.session_state['recommendations'] = []
        st.session_state['use_coupon'] = False
        st.session_state['selected_set'] = None
        set_page('home')
        st.rerun()

# --- 페이지: 메뉴판 보기 ---
def menu_board_page():
    st.title("📋 루시베이커리 메뉴판")
    
    # 데이터프레임을 활용하여 메뉴판 표시
    st.subheader("🍞 빵/디저트 메뉴")
    st.dataframe(
        menu_df[menu_df['category'].isin(['빵', '디저트'])][['name', 'price', 'sweetness', 'tags']].reset_index(drop=True),
        hide_index=True
    )
    
    st.subheader("🥗 식사 메뉴 (샌드위치/샐러드)")
    st.dataframe(
        menu_df[menu_df['category'].isin(['샌드위치', '샐러드'])][['name', 'price', 'sweetness', 'tags']].reset_index(drop=True),
        hide_index=True
    )
    
    st.info("💡 음료 메뉴는 CSV 파일에 없어 포함되지 않았습니다. (데이터 업데이트 필요)")
    
    if st.button("🏠 추천 서비스로 돌아가기"):
        set_page('recommend')
        st.rerun()

# --- 페이지: 주문 이력 확인 ---
def order_history_page():
    st.title("📚 과거 주문 이력")
    phone = st.session_state['phone_number']
    
    if phone in st.session_state['user_db']:
        history = st.session_state['user_db'][phone]['orders']
        st.markdown(f"**👤 고객님 ({phone})의 총 주문 횟수: {len(history)}회**")
        
        if history:
            # 최신 주문이 위로 오도록 역순 출력
            for order in reversed(history):
                st.markdown(f"---")
                st.markdown(f"**주문 번호**: {order['order_id']} | **주문일시**: {order['date']}")
                st.markdown(f"**메뉴**: {order['items']}")
        else:
            st.info("아직 주문 이력이 없습니다.")
            
    if st.button("🏠 추천 서비스로 돌아가기"):
        set_page('recommend')
        st.rerun()

# --- 메인 앱 로직 ---
def main():
    # 1. 앱 제목 변경
    st.set_page_config(page_title="루시베이커리 메뉴 추천 서비스", layout="centered")

    # 페이지 라우팅
    if st.session_state['page'] == 'home':
        home_page()
    elif st.session_state['page'] == 'recommend':
        recommend_page()
    elif st.session_state['page'] == 'menu_board':
        menu_board_page()
    elif st.session_state['page'] == 'order_history':
        order_history_page()
    elif st.session_state['page'] == 'order_complete':
        order_complete_page()

if __name__ == "__main__":
    main()
