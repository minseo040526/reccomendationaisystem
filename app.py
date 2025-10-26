
# -*- coding: utf-8 -*-
import os, time, itertools, re
import datetime as dt
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Lucy Bakery Menu Recommendation (Robust Tags)', layout='wide')

# ---------- DATA ----------
@st.cache_data
def load_menu(path: str):
    # Read as string to avoid dtype surprises
    df = pd.read_csv(path, dtype=str).fillna("")
    # Normalize known columns
    rename_map = {c:c.strip() for c in df.columns}
    df.rename(columns=rename_map, inplace=True)
    required = ["category","name","price","sweetness"]
    for col in required:
        if col not in df.columns:
            st.error(f"menu.csv에 '{col}' 컬럼이 필요합니다.")
            st.stop()

    # --- Robust tag ingestion ---
    # Collect everything after the known columns into one 'tags_joined'
    known = set(required + ["tags"])
    extra_cols = [c for c in df.columns if c not in known]
    if "tags" in df.columns:
        base = df["tags"].astype(str)
    else:
        base = pd.Series([""]*len(df))
    if extra_cols:
        joined = base.copy()
        for c in extra_cols:
            joined = joined + "," + df[c].astype(str)
        tags_joined = joined
    else:
        tags_joined = base

    # Split by comma/semicolon/pipe/slash/space and remove ALL '#'
    def to_list(s: str):
        tokens = re.split(r"[,\|/; ]+", str(s))
        out = []
        for t in tokens:
            t = re.sub(r"#", "", t).strip()
            if t and t.lower() != "nan":
                out.append(t)
        return out
    tags_list = tags_joined.apply(to_list)

    # Cast numeric fields
    df_num = df.copy()
    df_num["price"] = pd.to_numeric(df_num["price"], errors="coerce").fillna(0).astype(int)
    df_num["sweetness"] = pd.to_numeric(df_num["sweetness"], errors="coerce").fillna(0).astype(int)
    df_num["tags_list"] = tags_list

    # popularity flag
    def is_popular(tags):
        s = set(tags)
        return ("인기" in s) or ("인기메뉴" in s) or ("popular" in s)
    df_num["popular"] = df_num["tags_list"].apply(is_popular)
    return df_num

MENU = load_menu("menu.csv")
BAKERY_CATS = {"빵","샌드위치","샐러드","디저트"}
DRINK_CATS = {"커피","라떼","에이드","스무디","티"}

# Tag universe (from data)
ALL_TAGS = sorted({t for row in MENU["tags_list"] for t in row if t})
DISPLAY_TAGS = [f"#{t}" for t in ALL_TAGS] if ALL_TAGS else []

# ---------- UTILS ----------
def gen_order_code():
    return f"LUCY-{dt.datetime.now().strftime('%Y%m%d')}-{str(int(time.time()))[-4:]}"

def score_item(row, chosen_tags, target_sweetness):
    item_tags = set(row["tags_list"])
    tag_match = len(item_tags & set(chosen_tags))
    diff = abs(int(row["sweetness"]) - int(target_sweetness))
    sweet_score = max(0, 3 - diff)
    popular_bonus = 3 if row.get("popular", False) else 0
    return tag_match*3 + sweet_score + popular_bonus

def ranked_items(df, chosen_tags, sweet):
    if df.empty:
        return df.assign(_score=[])
    sc = df.apply(lambda r: score_item(r, chosen_tags, sweet), axis=1)
    return df.assign(_score=sc).sort_values(["_score","price"], ascending=[False, True]).reset_index(drop=True)

def recommend_combos(df, chosen_tags, sweet, budget, topk=3):
    cand = ranked_items(df, chosen_tags, sweet).head(12)
    combos, idxs = [], list(cand.index)
    for r in range(1, 4):
        for ids in itertools.combinations(idxs, r):
            items = cand.loc[list(ids)]
            total = int(items["price"].sum())
            if total <= budget:
                score = float(items["_score"].sum())
                combos.append((items, total, score, r))
    if not combos:
        return []
    combos.sort(key=lambda x: (-x[2], x[1], -x[3]))
    out, seen = [], set()
    for items, total, score, r in combos:
        sig = tuple(sorted(items["name"].tolist()))
        if sig in seen: 
            continue
        seen.add(sig); out.append((items, total, score, r))
        if len(out) == topk: 
            break
    return out

def show_combo(idx, items, total, budget):
    with st.container():
        st.markdown(f"### 세트 {idx} · 합계 **₩{total:,}** / 예산 ₩{int(budget):,}")
        cols = st.columns(min(4, len(items)))
        for i, (_, r) in enumerate(items.iterrows()):
            with cols[i % len(cols)]:
                star = " ⭐" if (isinstance(r.get('popular'), (bool, int)) and r.get('popular')) else ""
                st.markdown(f"- **{r['name']}**{star}")
                st.caption(f"{r['category']} · ₩{int(r['price']):,} · 당도 {int(r['sweetness'])}")
                tagtxt = ', '.join([f"#{t}" for t in r['tags_list']]) if r['tags_list'] else '-'
                st.text(tagtxt)

# ---------- HEADER ----------
st.title("AI 메뉴 추천 서비스")

# Router: confirmation
if st.session_state.get("view") == "confirm":
    st.success(f"주문 완료! 주문번호: **{st.session_state.get('order_code','-')}**")
    total = st.session_state.get("order_total", 0)
    names = st.session_state.get("order_names", [])
    if names:
        st.markdown("**주문 내역**")
        for n in names:
            st.markdown(f"- {n}")
    st.markdown(f"**합계**: ₩{int(total):,}")
    if st.button("처음으로 돌아가기"):
        st.session_state["view"] = None
        for k in ["order_code","order_total","order_names"]:
            st.session_state[k] = None
        st.rerun()
    st.stop()

# ---------- TABS ----------
tab1, tab2, tab3 = st.tabs(["🥐 베이커리 추천", "☕ 음료 추천", "📋 메뉴판"])

with tab1:
    st.subheader("예산 안에서 가능한 조합 3세트 (1~3개 자동)")
    c1, c2 = st.columns([1,3])
    with c1:
        budget = st.number_input("총 예산(₩)", 0, 200000, 20000, step=1000)
    with c2:
        st.caption("예산에 따라 세트 구성 수량이 1~3개로 자동 조정됩니다.")
    sweet = st.slider("당도 (0~5)", 0, 5, 2)

    if "selected_tags_disp" not in st.session_state:
        st.session_state["selected_tags_disp"] = []
        st.session_state["selected_tags_prev"] = []

    def enforce_max3():
        cur = st.session_state["selected_tags_disp"]
        if len(cur) > 3:
            st.session_state["selected_tags_disp"] = st.session_state["selected_tags_prev"]
            st.toast("태그는 최대 3개까지 선택할 수 있어요.", icon="⚠️")
        else:
            st.session_state["selected_tags_prev"] = cur

    st.caption("※ 태그가 안 보이면 '캐시 비우기' 버튼을 누르고 새로고침하세요.")
    if st.button("캐시 비우기"):
        st.cache_data.clear()
        st.rerun()

    selected_tags_disp = st.multiselect(
        "취향 태그 (최대 3개)",
        [f"#{t}" for t in ALL_TAGS],
        key="selected_tags_disp",
        on_change=enforce_max3
    )
    chosen_tags = [t.lstrip("#") for t in selected_tags_disp]

    if st.button("조합 3세트 추천받기 🍞"):
        bakery_df = MENU[MENU["category"].isin(BAKERY_CATS)].copy()
        if bakery_df.empty:
            st.error("베이커리/샌드위치/샐러드/디저트 데이터가 비어 있습니다.")
        elif bakery_df["price"].min() > budget:
            st.warning("예산이 너무 낮아요. 최소 한 개의 품목 가격보다 높게 설정해주세요.")
        else:
            results = recommend_combos(bakery_df, chosen_tags, sweet, int(budget), topk=3)
            if not results:
                st.warning("조건에 맞는 조합을 만들 수 없어요. 예산이나 태그를 조정해보세요.")
            else:
                for i, (items, total, score, r) in enumerate(results, start=1):
                    show_combo(i, items, total, budget)
                    with st.form(key=f'order_form_{i}', clear_on_submit=False):
                        submit = st.form_submit_button(f"세트 {i} 주문하기 (데모)")
                        if submit:
                            oc = gen_order_code()
                            st.session_state["order_code"] = oc
                            st.session_state["order_total"] = int(total)
                            st.session_state["order_names"] = items["name"].tolist()
                            st.session_state["view"] = "confirm"
                            st.rerun()

with tab2:
    st.subheader("카테고리 + 당도만으로 간단 추천 (분리 동작)")
    drink_cat = st.selectbox("음료 카테고리", sorted(DRINK_CATS))
    drink_sweet = st.slider("원하는 당도 (0~5)", 0, 5, 3, key="drink_sweet")
    if st.button("음료 추천받기 ☕️"):
        pool = MENU[(MENU["category"] == drink_cat)].copy()
        ranked = ranked_items(pool, [], drink_sweet)
        if ranked.empty:
            st.info("해당 카테고리 데이터가 없습니다.")
        else:
            st.markdown(f"**{drink_cat} TOP3** (인기 가중치 반영)")
            for _, r in ranked.head(3).iterrows():
                star = " ⭐" if r.get("popular") else ""
                st.markdown(f"- **{r['name']}**{star} · ₩{int(r['price']):,} · 당도 {int(r['sweetness'])}")

with tab3:
    st.subheader("메뉴판 이미지")
    imgs = [p for p in ["menu_board_1.png", "menu_board_2.png"] if os.path.exists(p)]
    if imgs:
        st.image(imgs, use_container_width=True, caption=[f"메뉴판 {i+1}" for i in range(len(imgs))])
    else:
        st.info("앱 폴더에 menu_board_1.png, menu_board_2.png 넣으면 이미지로 표시됩니다.")
        with st.expander("데이터 요약(관리자용) 보기"):
            st.dataframe(MENU[["category","name","price","sweetness","tags"]].reset_index(drop=True), hide_index=True)

st.divider()
st.caption("© 2025 Lucy Bakery")

