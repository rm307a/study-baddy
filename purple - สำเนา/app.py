import os
import time
import html as html_lib
from datetime import date
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv

from db_service import (
    init_db, register_user, login_user,
    get_user_subjects, add_subject_folder, set_subject_term,
    save_uploaded_files_to_subject, list_files_in_subject,
    log_daily_habit, get_habit_dataframe, calculate_study_streak,
    save_exam_result, get_exam_history_df,
    NO_TERM_LABEL, current_term_label, term_options, term_sort_key,
    ensure_default_habits, get_habits, add_habit, delete_habit, set_habit_check, get_habit_checks,
    get_active_focus, start_focus, stop_focus, get_focus_today,
    save_topic_results, get_subject_topic_stats, get_legacy_weak_topics,
    get_subject_overview, save_subject_overview,
)
from exam_service import extract_text_from_file_paths, generate_mock_exam
from stats_service import analyze_exam_performance, classify_topics
from ai_service import generate_ai_tutor_feedback, chat_with_study_buddy, generate_subject_overview
from ui_components import (
    HEATMAP_CSS, HEATMAP_LEGEND_HTML, FOCUS_WIDGET_HEIGHT,
    fmt_duration, heatmap_range, levels_for_all, levels_for_habit,
    build_heatmap_html, build_focus_widget_html,
)

load_dotenv()
init_db()

st.set_page_config(page_title="Smart Study Buddy & Analytics 🌸", page_icon="🌸", layout="wide")

# ตกแต่ง CSS โทนพาสเทลน่ารัก สบายตา
st.markdown("""
<style>
    .cute-card {
        background: linear-gradient(135deg, #fff5f8 0%, #f3e8ff 100%);
        border: 2px solid #fbcfe8;
        border-radius: 18px;
        padding: 18px;
        margin-bottom: 14px;
        box-shadow: 0 4px 10px rgba(244, 114, 182, 0.08);
    }
    .skill-badge {
        display: inline-block;
        background-color: #fce7f3;
        color: #be185d;
        padding: 4px 12px;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)
st.markdown(f"<style>{HEATMAP_CSS}</style>", unsafe_allow_html=True)

HABIT_WEEKS = 26  # ตาราง Habit ย้อนหลังประมาณ 6 เดือน


def esc(text) -> str:
    return html_lib.escape(str(text))


def topic_list_md(items: list, numbered: bool = False, limit: int = 8) -> str:
    """แปลงรายชื่อหัวข้อเป็นรายการ Markdown (แสดงสูงสุด limit ข้อ ที่เหลือสรุปเป็นจำนวน)"""
    shown = items[:limit]
    lines = [f"{i}. {t}" if numbered else f"- {t}" for i, t in enumerate(shown, 1)]
    if len(items) > limit:
        lines.append(f"\n_...และอีก {len(items) - limit} หัวข้อ_")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Callback ของปุ่ม/ช่องติ๊ก (รันก่อนสคริปต์รอบใหม่ ตัวเลขด้านบนจึงอัปเดตทันที)
# ------------------------------------------------------------------
def cb_start_focus(email: str):
    start_focus(email)


def cb_stop_focus(email: str):
    st.session_state.focus_last = stop_focus(email)


def cb_toggle_habit(email: str, habit_id: int, day_str: str, widget_key: str):
    set_habit_check(email, habit_id, day_str, bool(st.session_state.get(widget_key)))


# กำหนด Session State เริ่มต้น
if "user" not in st.session_state:
    st.session_state.user = None
if "questions" not in st.session_state:
    st.session_state.questions = []
if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0
if "responses" not in st.session_state:
    st.session_state.responses = []
if "question_start_time" not in st.session_state:
    st.session_state.question_start_time = None
if "exam_finished" not in st.session_state:
    st.session_state.exam_finished = False
if "ai_feedback" not in st.session_state:
    st.session_state.ai_feedback = None
if "active_subject" not in st.session_state:
    st.session_state.active_subject = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {"role": "assistant", "content": "สวัสดีค่ะ! น้อง Study Buddy 🌸 พร้อมช่วยติวแล้วค่ะ ลองกดคำถามด่วนด้านล่าง หรือพิมพ์ถามเจาะรายข้อ เช่น **'ข้อ 2 ช่วยอธิบายโจทย์หน่อย'** หรือ **'ฉันอ่อนเรื่องอะไร ควรอ่านอะไรก่อนสอบ'** ได้เลยนะคะ!"}
    ]

# ==============================================================================
# ส่วนที่ 1: หน้า Login & Register (Authentication Gate)
# ==============================================================================
if st.session_state.user is None:
    col_l, col_center, col_r = st.columns([1, 1.4, 1])
    with col_center:
        st.markdown("""
        <div class="cute-card" style="text-align:center;">
            <h2>🌸 Smart Study Buddy & Analytics</h2>
            <p>ระบบคลังสไลด์แยกวิชา จำลองการสอบจับเวลา ติดตามการเรียนด้วย Study Tracker และ AI ติวเตอร์ส่วนตัว</p>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_reg = st.tabs(["🔑 เข้าสู่ระบบ (Login)", "✨ สมัครสมาชิกใหม่ (Register)"])

        with tab_login:
            with st.form("login_form"):
                email_in = st.text_input("📧 อีเมล (Email)", placeholder="student@kmitl.ac.th")
                pw_in = st.text_input("🔒 รหัสผ่าน (Password)", type="password")
                sub_login = st.form_submit_button("เข้าสู่ระบบ 🚀", type="primary", use_container_width=True)
                if sub_login:
                    ok, res = login_user(email_in, pw_in)
                    if ok:
                        st.session_state.user = res
                        st.rerun()
                    else:
                        st.error(res)

        with tab_reg:
            with st.form("register_form"):
                name_reg = st.text_input("🎀 ชื่อเล่น / ชื่อที่ใช้แสดง", placeholder="เช่น น้องรามิล")
                email_reg = st.text_input("📧 อีเมล (Email)", placeholder="student@kmitl.ac.th")
                pw_reg = st.text_input("🔒 ตั้งรหัสผ่าน (อย่างน้อย 6 ตัวอักษร)", type="password")
                sub_reg = st.form_submit_button("สมัครสมาชิก ✨", type="primary", use_container_width=True)
                if sub_reg:
                    ok, msg = register_user(email_reg, pw_reg, name_reg)
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
    st.stop()

# ==============================================================================
# ส่วนที่ 2: แถบด้านข้าง (Sidebar) เมื่อ Login สำเร็จแล้ว
# ==============================================================================
user_email = st.session_state.user["email"]
user_name = st.session_state.user["name"]
streak_days = calculate_study_streak(user_email)
focus_today = get_focus_today(user_email)

with st.sidebar:
    st.markdown(f"""
    <div class="cute-card">
        <h4>👋 สวัสดีค่ะ คุณ {user_name}!</h4>
        <p style="margin:0;">📧 {user_email}</p>
        <p style="margin-top:8px; font-size:1.1rem;">🔥 <b>ต่อเนื่อง {streak_days} วัน</b></p>
    </div>
    """, unsafe_allow_html=True)

    st.header("⚙️ ตั้งค่า AI")
    api_key_input = st.text_input("GEMINI_API_KEY (เว้นว่างได้ถ้าอยู่ใน .env)", type="password")
    default_env_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    model_options = ["gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.6-flash"]
    if default_env_model not in model_options:
        model_options.insert(0, default_env_model)
    selected_model = st.selectbox("🤖 โมเดล Gemini", options=model_options, index=model_options.index(default_env_model))

    st.divider()
    if st.button("🚪 ออกจากระบบ (Logout)", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# หัวข้อหลักของหน้าเว็บ
st.title("🌸 Smart Study Buddy: คลังวิชา จำลองสอบ & ติดตามพัฒนาการ")

# แบ่งเป็น 4 เมนูหลัก (Tabs)
tab_habit, tab_folder, tab_exam, tab_chat = st.tabs([
    "🌱 1. Study Tracker",
    "📁 2. โฟลเดอร์วิชา & คลังสไลด์",
    "📝 3. ห้องสอบจำลอง",
    "💬 4. แชทถาม AI Tutor (ถามโจทย์/รีวิวพัฒนาการ)"
])

# ==============================================================================
# TAB 1: Study Tracker (สถิติ + บันทึกการเรียน + โฟกัส + Habit + สรุปรายวิชา + Radar)
# ==============================================================================
with tab_habit:
    today = date.today()
    grid_start, _ = heatmap_range(today, HABIT_WEEKS)

    ensure_default_habits(user_email)
    df_habit = get_habit_dataframe(user_email)
    df_exam_hist = get_exam_history_df(user_email)
    habits = get_habits(user_email)
    active_focus_start = get_active_focus(user_email)

    st.subheader("🌱 Study Tracker")

    total_mins = int(df_habit["study_minutes"].sum()) if not df_habit.empty else 0
    total_qs = int(df_habit["questions_done"].sum()) if not df_habit.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔥 ต่อเนื่อง", f"{streak_days} วัน")
    c2.metric("🎧 โฟกัสวันนี้", fmt_duration(focus_today["total_sec"]))
    c3.metric("⏱️ เวลาเรียนสะสม", f"{total_mins} นาที")
    c4.metric("✅ โจทย์ที่ทำ", f"{total_qs} ข้อ")

    h_col1, h_col2 = st.columns([1.2, 1.5])

    # ---------- ซ้าย: บันทึกการเรียนเพิ่มเติม (เหมือนเดิม) ----------
    with h_col1:
        with st.form("habit_form"):
            st.markdown("**📌 วันนี้อ่านหนังสือหรือทบทวนไปกี่นาทีคะ?**")
            add_min = st.number_input("⏱️ เวลาอ่านหนังสือที่เพิ่มวันนี้ (นาที)", min_value=0, max_value=600, value=30, step=15)
            add_q = st.number_input("✍️ จำนวนโจทย์ที่ฝึกทำเพิ่มข้างนอก (ข้อ)", min_value=0, max_value=200, value=0, step=5)
            note_in = st.text_input("💖 โน้ตสั้นๆ ถึงตัวเองวันนี้", placeholder="เช่น วันนี้อ่านเรื่อง Docker เข้าใจแล้ว!")
            if st.form_submit_button("✨ บันทึกความขยันวันนี้!", type="primary", use_container_width=True):
                log_daily_habit(user_email, add_minutes=add_min, add_questions=add_q, note=note_in)
                st.success("บันทึกสถิติวันนี้เรียบร้อยแล้ว เก่งมากเลยค่ะ! 🌸")
                st.rerun()

    # ---------- ขวา: โหมดโฟกัส (จับเวลา + เอฟเฟกต์ดอกไม้/แมว) ----------
    with h_col2:
        st.markdown("**🎧 โหมดโฟกัส**")
        if active_focus_start is not None:
            components.html(build_focus_widget_html("running", start_ts=active_focus_start), height=FOCUS_WIDGET_HEIGHT)
            st.button("⏹️ หยุดโฟกัส (Stop)", type="primary", use_container_width=True,
                      on_click=cb_stop_focus, args=(user_email,), key="focus_stop_btn")
        else:
            last_focus = st.session_state.pop("focus_last", None)
            if last_focus:
                done_text = f"รอบนี้โฟกัสไป {fmt_duration(last_focus['duration_sec'], with_seconds=True)} 🌸"
                if last_focus["capped"]:
                    done_text += " (นับสูงสุดรอบละ 6 ชั่วโมง)"
                components.html(build_focus_widget_html("done", done_text=done_text), height=FOCUS_WIDGET_HEIGHT)
            else:
                components.html(build_focus_widget_html("idle"), height=FOCUS_WIDGET_HEIGHT)
            st.button("▶️ เริ่มโฟกัส", type="primary", use_container_width=True,
                      on_click=cb_start_focus, args=(user_email,), key="focus_start_btn")
        st.caption(
            f"วันนี้โฟกัสไปแล้ว **{fmt_duration(focus_today['total_sec'], with_seconds=True)}** · {focus_today['rounds']} รอบ"
            + (" (ยังไม่รวมรอบที่กำลังโฟกัส)" if active_focus_start is not None else "")
        )

    # ---------- Habit Tracker แบบ GitHub-style ----------
    st.divider()
    st.subheader("🌷 Habit Tracker")
    st.caption("ติ๊กเองได้ทุกวัน ยิ่งทำบ่อย ช่องยิ่งเข้ม (ย้อนหลังประมาณ 6 เดือน)")

    habit_checks = get_habit_checks(user_email, since=grid_start.isoformat())
    t_col, g_col = st.columns([1, 2.4])

    with t_col:
        sel_date = st.date_input("📅 วันที่ที่ต้องการติ๊ก", value=today, min_value=grid_start, max_value=today, key="habit_date")
        sel_str = sel_date.isoformat()

        if habits:
            st.markdown("**ติ๊กสิ่งที่ทำแล้ว:**")
            for h in habits:
                ck = f"hchk_{h['id']}_{sel_str}"
                st.checkbox(
                    h["name"],
                    value=(sel_str in habit_checks.get(h["id"], set())),
                    key=ck,
                    on_change=cb_toggle_habit,
                    args=(user_email, h["id"], sel_str, ck),
                )
        else:
            st.info("ยังไม่มี habit เพิ่มอันแรกได้ด้านล่างเลยค่ะ 🌷")

        with st.form("add_habit_form", clear_on_submit=True):
            new_habit_name = st.text_input("➕ เพิ่ม habit ใหม่", placeholder="เช่น 🧘 ทบทวนก่อนนอน")
            if st.form_submit_button("เพิ่ม habit", use_container_width=True):
                ok, msg = add_habit(user_email, new_habit_name)
                if ok:
                    st.rerun()
                else:
                    st.warning(msg)

        if habits:
            with st.expander("⚙️ จัดการ habit"):
                del_name = st.selectbox("เลือก habit ที่ต้องการลบ", [h["name"] for h in habits], key="del_habit_sel")
                del_confirm = st.checkbox("ยืนยันลบ (ประวัติการติ๊กของ habit นี้จะหายด้วย)", key="del_habit_confirm")
                if st.button("🗑️ ลบ habit นี้", key="del_habit_btn"):
                    if del_confirm:
                        delete_habit(user_email, next(h["id"] for h in habits if h["name"] == del_name))
                        st.rerun()
                    else:
                        st.warning("ติ๊กยืนยันก่อนลบนะคะ")

    with g_col:
        if habits:
            st.markdown("<div style='font-weight:600;'>🌈 ภาพรวมทุก habit</div>", unsafe_allow_html=True)
            all_levels = levels_for_all(habit_checks, [h["id"] for h in habits])
            st.markdown(build_heatmap_html(all_levels, today, HABIT_WEEKS), unsafe_allow_html=True)
            for h in habits:
                done_days = len(habit_checks.get(h["id"], set()))
                st.markdown(
                    f"<div style='font-weight:600;'>{esc(h['name'])} <span style='font-weight:400;color:#9ca3af;'>· ทำแล้ว {done_days} วัน</span></div>",
                    unsafe_allow_html=True,
                )
                st.markdown(build_heatmap_html(levels_for_habit(habit_checks.get(h["id"], set())), today, HABIT_WEEKS),
                            unsafe_allow_html=True)
            st.markdown(HEATMAP_LEGEND_HTML, unsafe_allow_html=True)

    # ---------- สรุปรายวิชา (เลือกโฟลเดอร์ดูทีละวิชา) + Radar รายเทอม ----------
    st.divider()
    st.subheader("🌟 สรุปรายวิชา")

    all_subjects = get_user_subjects(user_email)
    if not all_subjects:
        st.info("ยังไม่มีโฟลเดอร์วิชา สร้างได้ที่แท็บ 2 เลยค่ะ 📁")
    else:
        subj_names = [s["name"] for s in all_subjects]
        sel_subj = st.selectbox("📂 เลือกโฟลเดอร์วิชาที่ต้องการดู", subj_names, key="summary_subject")
        subj_info = next(s for s in all_subjects if s["name"] == sel_subj)
        subj_files = list_files_in_subject(user_email, sel_subj)
        subj_exams = df_exam_hist[df_exam_hist["subject_name"] == sel_subj]

        st.markdown(
            f'<div class="cute-card"><h4>{esc(subj_info["icon"])} {esc(sel_subj)}</h4>'
            f'<p style="margin:0;">🗓️ {esc(subj_info["term"] or NO_TERM_LABEL)} &nbsp;·&nbsp; '
            f'📄 สไลด์ {len(subj_files)} ไฟล์ &nbsp;·&nbsp; 📝 สอบแล้ว {len(subj_exams)} ครั้ง</p></div>',
            unsafe_allow_html=True,
        )

        topic_groups = classify_topics(
            get_subject_topic_stats(user_email, sel_subj),
            get_legacy_weak_topics(user_email, sel_subj),
        )
        has_topic_data = any(topic_groups.values())
        no_data_text = "ยังไม่มีข้อมูล ลองทำข้อสอบวิชานี้ที่แท็บ 3 ก่อนนะคะ" if not has_topic_data else "ยังไม่มีหัวข้อในกลุ่มนี้"

        col_strong, col_weak, col_more = st.columns(3)
        with col_strong:
            st.markdown("##### 💪 เก่งเรื่อง")
            if topic_groups["strong"]:
                st.markdown(topic_list_md(topic_groups["strong"]))
            else:
                st.caption(no_data_text)
        with col_weak:
            st.markdown("##### 🌧️ ยังอ่อนเรื่อง")
            if topic_groups["weak"]:
                st.markdown(topic_list_md(topic_groups["weak"]))
            else:
                st.caption(no_data_text)
        with col_more:
            st.markdown("##### 📚 ควรศึกษาเพิ่ม")
            study_more = topic_groups["weak"] + topic_groups["mid"]
            if study_more:
                st.markdown(topic_list_md(study_more, numbered=True))
                st.caption("เรียงจากเรื่องที่ควรทบทวนก่อน")
            else:
                st.caption(no_data_text)

        # ให้ AI อ่านสไลด์แล้วสรุปว่า "วิชานี้คืออะไร" + แนะนำสิ่งที่ควรศึกษาเพิ่ม (กดเองเพื่อไม่เปลืองโควต้า)
        saved_overview = get_subject_overview(user_email, sel_subj)
        if saved_overview:
            st.markdown(saved_overview[0])
            st.caption(f"AI สรุปเมื่อ {saved_overview[1]}")
        elif subj_files:
            st.info("ยังไม่มีสรุปวิชานี้ กดปุ่มด้านล่างให้ AI อ่านสไลด์แล้วสรุปให้ได้เลยค่ะ ✨")
        else:
            st.info("อัปโหลดสไลด์เข้าโฟลเดอร์วิชานี้ก่อน (แท็บ 2) แล้วกลับมากดให้ AI สรุปวิชาได้เลยค่ะ")

        if subj_files and st.button("🔄 ให้ AI สรุปใหม่" if saved_overview else "✨ ให้ AI สรุปวิชานี้",
                                    key=f"overview_btn_{sel_subj}"):
            with st.spinner(f"กำลังอ่านสไลด์วิชา '{sel_subj}' และสรุปให้ค่ะ..."):
                try:
                    slide_text, _ = extract_text_from_file_paths(subj_files)
                    overview_text = generate_subject_overview(
                        sel_subj, slide_text,
                        topic_groups["strong"], topic_groups["mid"], topic_groups["weak"],
                        api_key=api_key_input, model=selected_model,
                    )
                    if overview_text.strip():
                        save_subject_overview(user_email, sel_subj, overview_text)
                        st.rerun()
                    else:
                        st.warning("AI ไม่ได้ส่งข้อความกลับมา ลองใหม่อีกครั้งนะคะ")
                except Exception as e:
                    st.error(f"สรุปวิชาไม่สำเร็จ: {e}")

        # ---------- Radar Chart เลือกเทอมได้ ----------
        st.divider()
        st.subheader("🕸️ เรดาร์สกิลรายเทอม")

        terms_in_use = sorted({(s["term"] or NO_TERM_LABEL) for s in all_subjects}, key=term_sort_key, reverse=True)
        this_term = current_term_label()
        sel_term = st.selectbox(
            "🗓️ เลือกเทอม", terms_in_use,
            index=terms_in_use.index(this_term) if this_term in terms_in_use else 0,
            key="radar_term",
        )

        term_subj_names = [s["name"] for s in all_subjects if (s["term"] or NO_TERM_LABEL) == sel_term]
        avg_by_subject = df_exam_hist.groupby("subject_name")["accuracy"].mean() if not df_exam_hist.empty else pd.Series(dtype=float)
        scored = [(n, round(float(avg_by_subject[n]), 1)) for n in term_subj_names if n in avg_by_subject.index]
        not_tested = [n for n in term_subj_names if n not in avg_by_subject.index]

        if scored:
            fig_radar = go.Figure(go.Scatterpolar(
                r=[v for _, v in scored],
                theta=[n for n, _ in scored],
                fill="toself",
                mode="lines+markers",
                line_color="#ec4899",
                name="ระดับความเข้าใจ",
            ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                showlegend=False,
                title=f"ระดับความเข้าใจรายวิชา · {sel_term}",
            )
            st.plotly_chart(fig_radar, use_container_width=True)
            st.caption("ค่าบนเรดาร์คิดจากผลสอบจำลองเฉลี่ยของแต่ละวิชา (เต็ม 100)")
            if len(scored) < 3:
                st.caption("💡 ถ้ามีวิชาที่เคยสอบในเทอมนี้ตั้งแต่ 3 วิชาขึ้นไป กราฟจะเห็นรูปร่างชัดขึ้นค่ะ")
        else:
            st.info("เทอมนี้ยังไม่มีวิชาที่เคยทำข้อสอบจำลองเลย ลองสอบที่แท็บ 3 แล้วกลับมาดูกราฟได้ค่ะ ✨")
        if not_tested and scored:
            st.caption("ยังไม่เคยสอบ (ยังไม่แสดงบนกราฟ): " + ", ".join(not_tested))

# ==============================================================================
# TAB 2: โฟลเดอร์วิชา & จัดการไฟล์สไลด์ (Subject Folders)
# ==============================================================================
with tab_folder:
    st.subheader("📁 จัดการโฟลเดอร์แยกวิชาและคลังสไลด์เรียน")

    f_col1, f_col2 = st.columns([1, 2])
    with f_col1:
        with st.form("create_subject_form"):
            st.markdown("**➕ สร้างโฟลเดอร์วิชาใหม่**")
            new_subj_name = st.text_input("ชื่อวิชา", placeholder="เช่น การวิเคราะห์การถดถอย")
            new_subj_icon = st.selectbox("เลือกไอคอนน่ารักๆ", ["📊", "🤖", "📐", "💻", "🧬", "📈", "🌸", "📚"])
            new_term_opts = term_options()
            new_subj_term = st.selectbox("🗓️ เทอมที่เรียน", new_term_opts, index=new_term_opts.index(current_term_label()))
            if st.form_submit_button("สร้างโฟลเดอร์วิชา ✨", use_container_width=True):
                ok, msg = add_subject_folder(user_email, new_subj_name, new_subj_icon, new_subj_term)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

    subjects = get_user_subjects(user_email)
    subject_names = [s["name"] for s in subjects]

    with f_col2:
        if not subject_names:
            st.info("ยังไม่มีโฟลเดอร์วิชา สร้างโฟลเดอร์แรกของคุณได้จากฟอร์มทางซ้ายเลยค่ะ 📁")
        else:
            selected_folder = st.selectbox("📂 เลือกโฟลเดอร์วิชาที่ต้องการจัดการไฟล์สไลด์:", options=subject_names)

            # ตั้ง/เปลี่ยนเทอมของวิชา (ใช้จัดกลุ่มใน Radar Chart ที่แท็บ 1)
            if selected_folder:
                cur_term = next((s["term"] for s in subjects if s["name"] == selected_folder), None)
                term_choices = [NO_TERM_LABEL] + term_options(extra=[cur_term] if cur_term else [])
                picked_term = st.selectbox(
                    "🗓️ เทอมของวิชานี้", term_choices,
                    index=term_choices.index(cur_term) if cur_term in term_choices else 0,
                    key=f"term_pick_{selected_folder}",
                )
                if picked_term != (cur_term or NO_TERM_LABEL):
                    set_subject_term(user_email, selected_folder, picked_term)
                    st.rerun()

            uploaded_slides = st.file_uploader(
                f"อัปโหลดไฟล์สไลด์ (PDF/TXT) เก็บเข้าโฟลเดอร์ '{selected_folder}' (เลือกหลายไฟล์พร้อมกันได้)",
                type=["pdf", "txt"],
                accept_multiple_files=True
            )
            if uploaded_slides:
                if st.button("💾 บันทึกไฟล์ลงโฟลเดอร์วิชานี้", type="primary"):
                    saved_paths = save_uploaded_files_to_subject(user_email, selected_folder, uploaded_slides)
                    st.success(f"บันทึกไฟล์ลงในโฟลเดอร์ '{selected_folder}' จำนวน {len(saved_paths)} ไฟล์เรียบร้อยแล้วค่ะ!")
                    st.rerun()

            existing_files = list_files_in_subject(user_email, selected_folder)
            st.markdown(f"**📄 ไฟล์สไลด์ที่มีอยู่ในโฟลเดอร์ `{selected_folder}` ({len(existing_files)} ไฟล์):**")
            if existing_files:
                for p in existing_files:
                    st.markdown(f"- 📘 `{os.path.basename(p)}`")
            else:
                st.caption("ยังไม่มีไฟล์สไลด์ในโฟลเดอร์วิชานี้ อัปโหลดไฟล์ด้านบนได้เลยค่ะ")

# ==============================================================================
# TAB 3: ห้องสอบจำลอง (Mock Exam)
# ==============================================================================
with tab_exam:
    subjects = get_user_subjects(user_email)
    subject_names = [s["name"] for s in subjects]

    if not st.session_state.questions and not subject_names:
        st.subheader("📝 ห้องสอบจำลอง")
        st.info("ยังไม่มีโฟลเดอร์วิชา ไปสร้างโฟลเดอร์และอัปโหลดสไลด์ที่แท็บ 2 ก่อน แล้วกลับมาสอบได้เลยค่ะ 📁")

    elif not st.session_state.questions:
        st.subheader("📝 เลือกโฟลเดอร์วิชาเพื่อเริ่มจำลองการสอบจับเวลา")
        exam_subj = st.selectbox("🎯 เลือกวิชาที่ต้องการทดสอบ:", options=subject_names, key="exam_subj_select")
        avail_files = list_files_in_subject(user_email, exam_subj)

        selected_file_paths = []
        if avail_files:
            file_map = {os.path.basename(p): p for p in avail_files}
            chosen_names = st.multiselect(
                "📚 เลือกไฟล์สไลด์ในโฟลเดอร์นี้ที่ต้องการนำมาออกข้อสอบ:",
                options=list(file_map.keys()),
                default=list(file_map.keys())
            )
            selected_file_paths = [file_map[n] for n in chosen_names]
        else:
            st.warning(f"ในโฟลเดอร์วิชา '{exam_subj}' ยังไม่มีไฟล์สไลด์เลยค่ะ คุณสามารถอัปโหลดด่วนด้านล่างนี้ได้เลย:")

        quick_uploads = st.file_uploader("⚡ หรืออัปโหลดไฟล์สไลด์ใหม่เข้าวิชานี้ทันที:", type=["pdf", "txt"], accept_multiple_files=True, key="quick_up")
        num_q = st.slider("🔢 จำนวนข้อสอบที่ต้องการสร้าง", min_value=3, max_value=20, value=5)

        if st.button("🚀 สร้างข้อสอบจำลองและเริ่มจับเวลา!", type="primary"):
            if quick_uploads:
                newly_saved = save_uploaded_files_to_subject(user_email, exam_subj, quick_uploads)
                selected_file_paths = list(set(selected_file_paths + newly_saved))

            if not selected_file_paths:
                st.error("กรุณาเลือกไฟล์สไลด์หรืออัปโหลดไฟล์อย่างน้อย 1 ไฟล์ก่อนเริ่มสอบนะคะ 🌸")
            else:
                with st.spinner(f"กำลังอ่านสไลด์วิชา '{exam_subj}' และให้ {selected_model} ออกข้อสอบ..."):
                    try:
                        slide_text, file_stats = extract_text_from_file_paths(selected_file_paths)
                        questions = generate_mock_exam(
                            slide_text,
                            subject_name=exam_subj,
                            num_questions=num_q,
                            api_key=api_key_input,
                            model=selected_model
                        )
                        st.session_state.active_subject = exam_subj
                        st.session_state.questions = questions
                        st.session_state.current_idx = 0
                        st.session_state.responses = []
                        st.session_state.exam_finished = False
                        st.session_state.ai_feedback = None
                        st.session_state.question_start_time = time.time()
                        st.rerun()
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาด: {e}")

    elif not st.session_state.exam_finished:
        q_list = st.session_state.questions
        idx = st.session_state.current_idx
        current_q = q_list[idx]

        st.markdown(f"#### 📚 วิชา: **{st.session_state.active_subject}**")
        st.progress((idx + 1) / len(q_list), text=f"ข้อที่ {idx + 1} จาก {len(q_list)} ข้อ")

        c_tag1, c_tag2 = st.columns(2)
        c_tag1.info(f"📌 **หมวดหมู่:** {current_q['topic']}")
        c_tag2.warning(f"🎯 **ระดับความยาก:** {current_q['difficulty']}")

        st.markdown(f"### ข้อที่ {idx + 1}: {current_q['question']}")
        selected_option = st.radio("เลือกคำตอบที่ถูกต้องที่สุด:", options=current_q["options"], key=f"radio_{idx}", index=None)

        btn_label = "ส่งกระดาษคำตอบและบันทึกสถิติ 📊" if idx == len(q_list) - 1 else "บันทึกและไปข้อถัดไป ➡️"
        if st.button(btn_label, type="primary"):
            if selected_option is None:
                st.warning("⚠️ กรุณาเลือกคำตอบก่อนกดไปข้อถัดไปนะคะ")
            else:
                elapsed_sec = round(time.time() - st.session_state.question_start_time, 2)
                is_correct = 1 if selected_option.strip() == current_q["correct_answer"].strip() else 0

                st.session_state.responses.append({
                    "id": current_q["id"],
                    "topic": current_q["topic"],
                    "difficulty": current_q["difficulty"],
                    "question": current_q["question"],
                    "user_answer": selected_option,
                    "correct_answer": current_q["correct_answer"],
                    "is_correct": is_correct,
                    "time_sec": elapsed_sec,
                    "explanation": current_q["explanation"]
                })

                if idx + 1 < len(q_list):
                    st.session_state.current_idx += 1
                    st.session_state.question_start_time = time.time()
                    st.rerun()
                else:
                    # คำนวณสถิติและบันทึกลงฐานข้อมูลทันทีที่ส่งข้อสอบ
                    df_raw = pd.DataFrame(st.session_state.responses)
                    stats_res = analyze_exam_performance(df_raw)
                    ov = stats_res["overall"]
                    weak_list = [t["topic"] for t in stats_res["topic_summary"] if t["accuracy"] < 70]
                    save_exam_result(
                        user_email,
                        st.session_state.active_subject,
                        ov["total_questions"],
                        ov["correct_answers"],
                        ov["accuracy_percent"],
                        ov["mean_time_sec"],
                        weak_list
                    )
                    # เก็บผลรายหัวข้อไว้สรุปว่าเก่ง/อ่อนเรื่องอะไรในแท็บ Study Tracker
                    save_topic_results(user_email, st.session_state.active_subject, stats_res["topic_summary"])
                    st.session_state.exam_finished = True
                    st.rerun()

    else:
        col_top1, col_top2 = st.columns([3, 1])
        col_top1.success(f"🎉 สอบวิชา **{st.session_state.active_subject}** เสร็จสมบูรณ์! บันทึกลง Study Tracker เรียบร้อยแล้วค่ะ")
        if col_top2.button("🔄 ทำข้อสอบชุดใหม่", use_container_width=True):
            st.session_state.questions = []
            st.session_state.exam_finished = False
            st.rerun()

        df_raw = pd.DataFrame(st.session_state.responses)
        stats_result = analyze_exam_performance(df_raw)
        ov = stats_result["overall"]
        df_det = stats_result["df_detailed"]

        # 1. Metric Cards: คะแนน / เวลาที่ทำไปทั้งหมด / เวลาเฉลี่ยต่อข้อ
        m1, m2, m3 = st.columns(3)
        m1.metric("🎯 คะแนนที่ได้", f"{ov['correct_answers']} / {ov['total_questions']} ข้อ")
        m2.metric("⏱️ เวลาที่ทำไป", fmt_duration(ov["total_time_sec"], with_seconds=True))
        m3.metric("⏱️ เวลาเฉลี่ยต่อข้อ", f"{ov['mean_time_sec']} วินาที")

        # 2. ตารางสรุปรายข้อและเฉลย (เรียงตามลำดับข้อที่ทำจริง ไม่ใช้เลข id ที่ AI สร้างมา)
        df_det["สถานะคำตอบ"] = df_det["is_correct"].map({1: "ตอบถูก ✅", 0: "ตอบผิด ❌"})
        df_show = df_det[["question", "topic", "difficulty", "time_sec", "สถานะคำตอบ", "user_answer", "correct_answer", "explanation"]].copy()
        df_show.insert(0, "Question No.", range(1, len(df_show) + 1))
        st.dataframe(
            df_show,
            use_container_width=True,
            hide_index=True,  # ซ่อนคอลัมน์ลำดับ 0,1,2,... ด้านหน้าสุด
            column_config={"question": st.column_config.TextColumn("question", width="large")},
        )

        # 3. ปุ่มให้ AI วิเคราะห์จุดอ่อนและติวเข้ม
        if st.button("🤖 ให้ AI วินิจฉัยจุดอ่อนและสรุปเนื้อหาติวเข้ม", type="primary"):
            with st.spinner("น้อง Study Buddy กำลังวิเคราะห์จุดอ่อนและสรุปเนื้อหาให้ค่ะ..."):
                wrong_q = df_det[df_det["is_correct"] == 0][
                    ["id", "topic", "question", "user_answer", "correct_answer", "explanation"]
                ].to_dict(orient="records")
                st.session_state.ai_feedback = generate_ai_tutor_feedback(
                    stats_result, wrong_q, api_key=api_key_input, model=selected_model
                )
        if st.session_state.ai_feedback:
            st.markdown(st.session_state.ai_feedback)

# ==============================================================================
# TAB 4: ช่องแชทคุยกับ AI Tutor (ถามโจทย์รายข้อ / สรุปผลรายวิชา / รีวิวพัฒนาการ)
# ==============================================================================
with tab_chat:
    st.subheader("💬 คุยกับน้อง Study Buddy AI (รู้จริงทุกข้อสอบและสถิติทุกวิชาของคุณ)")
    st.caption("กดปุ่มคำถามด่วนด้านล่าง หรือพิมพ์ถามเองได้เลย เช่น 'ข้อ 2 ช่วยอธิบายโจทย์หน่อย'")

    # ปุ่มคำถามด่วน: 3 คำถามที่ผู้ใช้น่าจะถามบ่อยที่สุด
    q_btn1, q_btn2, q_btn3 = st.columns(3)
    quick_prompt = None
    if q_btn1.button("🧠 ข้อที่ฉันตอบผิดคืออะไร ช่วยอธิบายหน่อย", use_container_width=True):
        quick_prompt = "ช่วยอธิบายข้อที่ฉันตอบผิดในข้อสอบชุดล่าสุด พร้อมเหตุผลว่าทำไมคำตอบที่ถูกต้องคือข้อนั้น ให้เข้าใจง่ายๆ หน่อยค่ะ"
    if q_btn2.button("📚 ฉันอ่อนเรื่องอะไร ควรอ่านอะไรก่อนสอบ", use_container_width=True):
        quick_prompt = "จากผลสอบทั้งหมดของฉัน ฉันอ่อนเรื่องอะไรบ้าง และควรทบทวนเรื่องไหนก่อนสอบจริง ช่วยเรียงลำดับความสำคัญให้หน่อยค่ะ"
    if q_btn3.button("📅 ช่วยวางแผนอ่านหนังสือ 7 วันให้หน่อย", use_container_width=True):
        quick_prompt = "จากสถิติการเรียนและผลสอบของฉัน ช่วยวางแผนอ่านหนังสือ 7 วันข้างหน้าให้หน่อยค่ะ ว่าแต่ละวันควรอ่านอะไร"

    # แสดงข้อความแชททั้งหมด
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_chat_in = st.chat_input("พิมพ์ถามได้เลย เช่น 'ข้อที่ฉันตอบผิดคืออะไร' หรือ 'สรุปผลวิชานี้ให้หน่อย'...")
    active_prompt = quick_prompt or user_chat_in

    if active_prompt:
        st.session_state.chat_messages.append({"role": "user", "content": active_prompt})
        with st.chat_message("user"):
            st.markdown(active_prompt)

        with st.chat_message("assistant"):
            with st.spinner("น้อง Study Buddy กำลังค้นข้อมูลการสอบและสถิติของคุณ..."):
                try:
                    hist_records = get_exam_history_df(user_email).to_dict(orient="records")
                    df_h = get_habit_dataframe(user_email)
                    habit_sum = {
                        "streak_days": streak_days,
                        "total_study_minutes": int(df_h["study_minutes"].sum()) if not df_h.empty else 0,
                        "total_questions_done": int(df_h["questions_done"].sum()) if not df_h.empty else 0,
                        "today_focus_minutes": int(focus_today["total_sec"] // 60),
                    }
                    reply = chat_with_study_buddy(
                        user_message=active_prompt,
                        chat_history=st.session_state.chat_messages,
                        current_exam_questions=st.session_state.questions,
                        current_exam_responses=st.session_state.responses,
                        exam_history_df_records=hist_records,
                        habit_summary=habit_sum,
                        api_key=api_key_input,
                        model=selected_model
                    )
                    st.markdown(reply)
                    st.session_state.chat_messages.append({"role": "assistant", "content": reply})
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการแชท: {e}")