import os
import json
import re
import time
import random
from openai import AzureOpenAI
from google import genai
from dotenv import load_dotenv

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    from pypdf import PdfReader
    HAS_FITZ = False

load_dotenv()


def extract_text_from_file_paths(file_paths: list[str], max_pages_to_read: int = 12, target_char_limit: int = 10000) -> tuple[str, dict]:
    """อ่านไฟล์ PDF แบบความเร็วสูง สกัดเฉพาะหน้าที่มีเนื้อหาชัดเจน"""
    selected_chunks = []
    file_stats = {"total_files": len(file_paths), "total_pages": 0, "files_detail": []}
    pages_quota_per_file = max(2, max_pages_to_read // max(1, len(file_paths)))

    for path in file_paths:
        filename = os.path.basename(path)

        if filename.lower().endswith(".pdf"):
            if HAS_FITZ:
                doc = fitz.open(path)
                num_pages = len(doc)
                file_stats["total_pages"] += num_pages
                file_stats["files_detail"].append({"name": filename, "pages": num_pages})

                if num_pages <= pages_quota_per_file:
                    indices = list(range(num_pages))
                else:
                    step = num_pages / pages_quota_per_file
                    indices = sorted(list(set(int(i * step) for i in range(pages_quota_per_file))))

                for idx in indices:
                    page_text = doc[idx].get_text("text").strip()
                    if len(page_text) > 30:
                        selected_chunks.append(f"\n--- [ไฟล์: {filename} | หน้า {idx+1}] ---\n{page_text[:850]}")
                doc.close()
            else:
                reader = PdfReader(path)
                num_pages = len(reader.pages)
                file_stats["total_pages"] += num_pages
                file_stats["files_detail"].append({"name": filename, "pages": num_pages})

                if num_pages <= pages_quota_per_file:
                    indices = list(range(num_pages))
                else:
                    step = num_pages / pages_quota_per_file
                    indices = sorted(list(set(int(i * step) for i in range(pages_quota_per_file))))

                for idx in indices:
                    page_text = (reader.pages[idx].extract_text() or "").strip()
                    if len(page_text) > 30:
                        selected_chunks.append(f"\n--- [ไฟล์: {filename} | หน้า {idx+1}] ---\n{page_text[:850]}")
        else:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                raw_content = f.read(4000).strip()
            file_stats["total_pages"] += 1
            file_stats["files_detail"].append({"name": filename, "pages": 1})
            if raw_content:
                selected_chunks.append(f"\n--- [ไฟล์: {filename} | หน้า 1] ---\n{raw_content}")

    if not selected_chunks:
        raise ValueError("ไม่พบข้อความในไฟล์ที่เลือก (ไฟล์อาจเป็นภาพสแกนล้วน)")

    combined = "".join(selected_chunks)
    return combined[:target_char_limit], file_stats


def call_ai_unified(prompt: str, primary_model: str = None, api_key: str = None) -> str:
    """
    ฟังก์ชันกลางสำหรับเรียก AI:
    1. ถ้าตั้งค่า AZURE_OPENAI_API_KEY ใน .env จะใช้ Azure OpenAI เป็นหลัก (ไม่ติดลิมิต 20 ครั้ง!)
    2. ถ้าไม่ได้ตั้งค่า Azure จะสลับไปใช้ Gemini API ตามปกติ
    """
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip().strip('"').strip("'")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().strip('"').strip("'")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini").strip().strip('"').strip("'")
    azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview").strip().strip('"').strip("'")

    # 1. เรียกผ่าน Azure OpenAI (ถ้าใส่ Key ของ Azure ไว้ใน .env)
    if azure_key and azure_endpoint and "ใส่_KEY" not in azure_key:
        azure_client = AzureOpenAI(
            api_key=azure_key,
            api_version=azure_version,
            azure_endpoint=azure_endpoint
        )
        response = azure_client.chat.completions.create(
            model=azure_deployment,
            messages=[
                {"role": "system", "content": "คุณคืออาจารย์และนักวิเคราะห์ข้อมูลการเรียนระดับมหาวิทยาลัย ตอบกลับด้วยข้อมูลที่ถูกต้องและแม่นยำ"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content or ""

    # 2. ถ้าไม่ได้ตั้งค่า Azure ให้เรียกผ่าน Gemini API
    raw_gemini_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip().strip('"').strip("'")
    if not raw_gemini_key:
        raise ValueError("🔑 กรุณาตั้งค่า AZURE_OPENAI_API_KEY หรือ GEMINI_API_KEY ในไฟล์ .env ก่อนนะคะ")

    keys_list = [k.strip() for k in raw_gemini_key.split(",") if k.strip()]
    clean_model = (primary_model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")).strip().strip('"').strip("'")

    last_err = None
    for k in keys_list:
        client = genai.Client(api_key=k)
        for m in [clean_model, "gemini-3.6-flash", "gemini-3.8-pro"]:
            try:
                resp = client.models.generate_content(model=m, contents=prompt)
                return resp.text or ""
            except Exception as e:
                last_err = e
                continue
    raise last_err


# คงชื่อฟังก์ชันเดิมไว้เพื่อให้ไฟล์ ai_service.py เรียกใช้งานร่วมกันได้ทันที
def clean_api_key(api_key: str = None) -> str:
    return (api_key or os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()

def call_gemini_smart(client, primary_model: str, prompt: str, config=None, api_key: str = None):
    class _TextWrapper:
        def __init__(self, text):
            self.text = text
    return _TextWrapper(call_ai_unified(prompt, primary_model=primary_model, api_key=api_key))


def _repair_and_parse_json(raw_text: str) -> list:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
    text = re.sub(r",\s*([\]}])", r"\1", text)
    return json.loads(text)


def generate_mock_exam(
    slide_text: str,
    subject_name: str = "ทั่วไป",
    num_questions: int = 5,
    api_key: str = None,
    model: str = None
) -> list:
    prompt = f"""
    สร้างข้อสอบปรนัย 4 ตัวเลือก วิชา "{subject_name}" จำนวน {num_questions} ข้อ จากเนื้อหาสไลด์ต่อไปนี้
    ห้ามใช้เครื่องหมายฟันหนูคู่ (") ภายในข้อความโจทย์หรือตัวเลือก ให้ใช้ฟันหนูเดี่ยว (') แทน

    ส่งกลับเป็น JSON Array เท่านั้น ห้ามมีคำอธิบายนอกกรอบ JSON ตามโครงสร้างนี้:
    [
      {{
        "id": 1,
        "topic": "หัวข้อย่อย",
        "difficulty": "จำ (Remember) หรือ เข้าใจ (Understand) หรือ วิเคราะห์ (Analyze)",
        "question": "โจทย์คำถาม",
        "options": ["A. ตัวเลือก 1", "B. ตัวเลือก 2", "C. ตัวเลือก 3", "D. ตัวเลือก 4"],
        "correct_answer": "A. ตัวเลือก 1",
        "explanation": "เฉลยสั้นกระชับ (อ้างอิง: ไฟล์ X หน้า Y)"
      }}
    ]

    เนื้อหาสไลด์:
    {slide_text}
    """

    raw_output = call_ai_unified(prompt, primary_model=model, api_key=api_key)
    return _repair_and_parse_json(raw_output)