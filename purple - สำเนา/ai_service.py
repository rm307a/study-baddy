import os
from google import genai
from dotenv import load_dotenv
from exam_service import call_gemini_smart, call_ai_unified, clean_api_key

load_dotenv()

def generate_ai_tutor_feedback(
    stats_result: dict,
    wrong_questions: list,
    api_key: str = None,
    model: str = None
) -> str:
    """ส่งผลสถิติและข้อที่ทำผิดไปให้ Gemini วิเคราะห์จุดอ่อน (พร้อมระบบสรุปอัตโนมัติหาก Server 503)"""
    key = clean_api_key(api_key)
    model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    client = genai.Client(api_key=key)

    prompt = f"""
    คุณคือ AI Learning Data Analyst และติวเตอร์ส่วนตัวที่พูดจาน่ารักอบอุ่นและให้กำลังใจผู้เรียน
    ห้ามคำนวณตัวเลขทางสถิติใหม่เองโดยเด็ดขาด ให้ใช้ตัวเลขจากผลการคำนวณของระบบ Python ด้านล่างนี้ในการวิเคราะห์เท่านั้น:

    [1. สถิติภาพรวมจากระบบ Python]
    {stats_result['overall']}

    [2. สถิติแยกตามหัวข้อ (Topic Summary)]
    {stats_result['topic_summary']}

    [3. การจำแนกพฤติกรรมการทำข้อสอบ]
    {stats_result['behavior_counts']}

    [4. รายละเอียดข้อที่ผู้เรียนทำผิด]
    {wrong_questions}

 กรุณาเขียนรายงานวิเคราะห์ผลโดยแบ่งหัวข้อดังนี้:
    1. **📊 Result (สรุปผลการสอบ):** สรุปคะแนนที่ได้ ความแม่นยำ (%) และเวลาเฉลี่ยที่ใช้ทำข้อสอบ
    2. **🔍 Insight (วิเคราะห์จุดแข็งและจุดอ่อน):** วิเคราะห์ว่าหัวข้อย่อยไหนที่ทำได้ดี และหัวข้อไหนที่ยังต้องทบทวนเพิ่ม
    3. **💡 Targeted Tutoring (สรุปเนื้อหาติวเข้มเฉพาะข้อที่ทำผิด):** อธิบายหลักการของข้อที่ทำผิดให้เข้าใจง่าย พร้อมระบุชื่อไฟล์และเลขหน้าสไลด์อ้างอิง
    4. **🌱 Recommendation & Action Plan (แผนการเตรียมตัวสอบ):** แนะนำลำดับความสำคัญในการอ่านหนังสือทบทวนก่อนสอบจริง
    """

    try:
        response = call_gemini_smart(client, model_name, prompt)
        return response.text or "Gemini ไม่ได้ส่งข้อความตอบกลับ"
    except Exception:
        ov = stats_result["overall"]
        wrong_text = "\n".join([f"- **หัวข้อ {w.get('topic')}:** ควรตอบ `{w.get('correct_answer')}` ({w.get('explanation')})" for w in wrong_questions]) or "- ตอบถูกครบทุกข้อ เก่งมากเลยค่ะ! 🎉"
        return f"""
### 🌸 รายงานวิเคราะห์ผลการสอบ (ประมวลผลจากสถิติ Python อัตโนมัติเนื่องจาก Gemini Server คิวเต็มชั่วคราว)
* **📊 Result (สรุปผลทางสถิติ):** คุณได้คะแนน **{ov['correct_answers']} / {ov['total_questions']} ข้อ ({ov['accuracy_percent']}%)** ใช้เวลาคิดเฉลี่ยข้อละ **{ov['mean_time_sec']} วินาที** (SD = {ov['sd_time_sec']} วินาที) และมีค่าสหสัมพันธ์ระหว่างเวลากับความถูกต้อง (Correlation) เท่ากับ **{ov['time_accuracy_correlation']}**
* **🔍 Insight (การวินิจฉัยพฤติกรรม):** สัดส่วนพฤติกรรมการทำข้อสอบของคุณคือ `{stats_result['behavior_counts']}`
* **💡 Targeted Tutoring (จุดที่ต้องทบทวนจากสไลด์):**
{wrong_text}
* **🌱 Recommendation:** แนะนำให้กลับไปทบทวนหน้าสไลด์ของหัวข้อที่ได้ความแม่นยำต่ำกว่า 70% แล้วลองกดทำข้อสอบซ้ำอีกครั้งเพื่ออัปเลเวลสกิลวิชานะคะ!
"""


def chat_with_study_buddy(
    user_message: str,
    chat_history: list,
    current_exam_questions: list,
    current_exam_responses: list,
    exam_history_df_records: list,
    habit_summary: dict,
    api_key: str = None,
    model: str = None
) -> str:
    key = clean_api_key(api_key)
    model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    client = genai.Client(api_key=key)

    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history[-4:]])

    prompt = f"""
    คุณคือ "Nong Study Buddy 🌸" ผู้ช่วยติวเตอร์ AI และนักวิเคราะห์ข้อมูลการเรียนส่วนตัว พูดจาไพเราะ น่ารัก สดใส
    ใช้ข้อมูลจริงของผู้เรียนด้านล่างนี้ในการตอบคำถาม:

    [A. ข้อสอบชุดล่าสุดที่เพิ่งทำ]
    โจทย์ทั้งหมด: {current_exam_questions}
    คำตอบของผู้ใช้: {current_exam_responses}

    [B. ประวัติการสอบทั้งหมดแยกตามวิชา]
    {exam_history_df_records}

    [C. สถิติความสม่ำเสมอในการเรียน (Study Tracker)]
    {habit_summary}

    [D. บทสนทนาก่อนหน้า]
    {history_text}

    คำถามจากผู้เรียน: "{user_message}"
    """

    try:
        response = call_gemini_smart(client, model_name, prompt)
        return response.text or "ขออภัยค่ะ ระบบไม่สามารถตอบกลับได้ในขณะนี้"
    except Exception:
        # กรณี Gemini Server 503 ให้ค้นคำตอบจากข้อมูลในเครื่องมาตอบทันที
        if current_exam_questions:
            q_summary = "\n".join([f"- **ข้อที่ {q['id']} ({q['topic']}):** {q['question']} ➡️ **เฉลย:** `{q['correct_answer']}` ({q['explanation']})" for q in current_exam_questions])
        else:
            q_summary = "ยังไม่มีข้อมูลข้อสอบชุดล่าสุดค่ะ"
        return f"""🌸 **(โหมดตอบกลับอัตโนมัติเนื่องจากเซิร์ฟเวอร์ Gemini มีผู้ใช้งานหนาแน่น 503)**

จากข้อมูลในระบบของคุณตอนนี้:
* 🔥 **สถิติการเรียน (Study Tracker):** อ่านต่อเนื่อง **{habit_summary.get('streak_days', 0)} วัน**, เวลาเรียนสะสม **{habit_summary.get('total_study_minutes', 0)} นาที**, ทำโจทย์ **{habit_summary.get('total_questions_done', 0)} ข้อ**
* 📝 **สรุปเฉลยและคำอธิบายของข้อสอบชุดล่าสุด:**
{q_summary}
"""


def generate_subject_overview(
    subject_name: str,
    slide_text: str,
    strong_topics: list,
    mid_topics: list,
    weak_topics: list,
    api_key: str = None,
    model: str = None
) -> str:
    """ให้ AI สรุปว่าวิชานี้คืออะไร + ควรศึกษาอะไรเพิ่ม (ไม่พูดถึงตัวเลขความแม่นยำ)"""
    prompt = f"""
    คุณคือติวเตอร์ประจำวิชา "{subject_name}" พูดจาอบอุ่น เข้าใจง่าย
    จากเนื้อหาสไลด์และข้อมูลจุดเก่ง/จุดอ่อนของผู้เรียนด้านล่าง ให้ตอบเป็น Markdown เท่านั้น โดยมี 2 หัวข้อตามนี้เป๊ะ:

    ### 📖 วิชานี้คืออะไร
    (อธิบาย 3-4 ประโยคว่าวิชานี้เรียนเกี่ยวกับอะไร มีหัวข้อหลักอะไรบ้าง)

    ### 📚 ควรศึกษาอะไรเพิ่ม
    (แนะนำ 3-5 ข้อ เรียงตามความสำคัญ โดยให้ความสำคัญกับหัวข้อที่ผู้เรียนยังอ่อนก่อน
     ถ้ายังไม่มีข้อมูลการสอบเลย ให้แนะนำหัวข้อสำคัญจากสไลด์ที่ควรอ่านก่อน และอ้างอิงชื่อไฟล์/เลขหน้าสไลด์ถ้ามี)

    ห้ามกล่าวถึงตัวเลขเปอร์เซ็นต์หรือความแม่นยำ ห้ามแต่งเนื้อหานอกเหนือจากสไลด์

    [หัวข้อที่ผู้เรียนทำได้ดี]: {strong_topics or 'ยังไม่มีข้อมูล'}
    [หัวข้อที่พอใช้ ควรทบทวนให้แม่นขึ้น]: {mid_topics or 'ยังไม่มีข้อมูล'}
    [หัวข้อที่ยังอ่อน]: {weak_topics or 'ยังไม่มีข้อมูล'}

    [เนื้อหาสไลด์]
    {slide_text}
    """
    return call_ai_unified(prompt, primary_model=model, api_key=api_key) or ""