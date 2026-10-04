import pandas as pd
import numpy as np

def analyze_exam_performance(df: pd.DataFrame) -> dict:
    """
    รับ DataFrame ผลการทำข้อสอบ มาคำนวณสถิติเชิงลึกด้วย Python
    คอลัมน์ใน df: ['id', 'topic', 'difficulty', 'is_correct', 'time_sec']
    """
    total_q = len(df)
    correct_q = int(df["is_correct"].sum())
    accuracy_pct = round((correct_q / total_q) * 100, 2) if total_q > 0 else 0.0

    # 1. สถิติเวลาที่ใช้ทำข้อสอบ (Descriptive Statistics)
    mean_time = round(float(df["time_sec"].mean()), 2)
    sd_time = round(float(df["time_sec"].std()), 2) if total_q > 1 else 0.0
    total_time = round(float(df["time_sec"].sum()), 2)

    # 2. คำนวณ Correlation ระหว่าง เวลาที่ใช้ทำ กับ ความถูกต้อง
    if total_q > 1 and df["is_correct"].nunique() > 1 and df["time_sec"].std() > 0:
        corr = round(float(df["time_sec"].corr(df["is_correct"])), 4)
    else:
        corr = 0.0

    # 3. จำแนกพฤติกรรมการทำข้อสอบรายข้อ (Behavioral Classification)
    # ใช้ค่ามัธยฐาน (Median) หรือเกณฑ์ขั้นต่ำเป็นตัวแบ่งความเร็ว
    threshold_time = max(mean_time, 10.0)
    
    behaviors = []
    for _, row in df.iterrows():
        if row["is_correct"] == 1 and row["time_sec"] <= threshold_time:
            behaviors.append("แม่นยำและคล่องแคล่ว (Mastered)")
        elif row["is_correct"] == 1 and row["time_sec"] > threshold_time:
            behaviors.append("ทำได้แต่ใช้เวลานาน (Need Practice)")
        elif row["is_correct"] == 0 and row["time_sec"] <= 5.0:
            behaviors.append("รีบตอบ/เดาสุ่ม/สะเพร่า (Careless/Guessing)")
        else:
            behaviors.append("ไม่เข้าใจเนื้อหาจุดนี้ (Knowledge Gap)")
            
    df["behavior"] = behaviors

    # 4. สรุปความแม่นยำและเวลาเฉลี่ยแยกตามหัวข้อ (Topic Grouping)
    topic_summary = (
        df.groupby("topic")
        .agg(
            total_questions=("id", "count"),
            correct_answers=("is_correct", "sum"),
            accuracy=("is_correct", lambda x: round(x.mean() * 100, 2)),
            avg_time_sec=("time_sec", lambda x: round(x.mean(), 2))
        )
        .reset_index()
    )

    # 5. สรุปความแม่นยำแยกตามระดับความยาก (Difficulty Grouping)
    diff_summary = (
        df.groupby("difficulty")
        .agg(
            total_questions=("id", "count"),
            accuracy=("is_correct", lambda x: round(x.mean() * 100, 2)),
            avg_time_sec=("time_sec", lambda x: round(x.mean(), 2))
        )
        .reset_index()
    )

    return {
        "overall": {
            "total_questions": total_q,
            "correct_answers": correct_q,
            "accuracy_percent": accuracy_pct,
            "total_time_sec": total_time,
            "mean_time_sec": mean_time,
            "sd_time_sec": sd_time,
            "time_accuracy_correlation": corr
        },
        "df_detailed": df,
        "topic_summary": topic_summary.to_dict(orient="records"),
        "difficulty_summary": diff_summary.to_dict(orient="records"),
        "behavior_counts": df["behavior"].value_counts().to_dict()
    }


# เกณฑ์แบ่งระดับหัวข้อ (ใช้เฉพาะจัดกลุ่มเก่ง/พอใช้/อ่อน ไม่แสดงตัวเลขให้ผู้ใช้เห็น)
STRONG_MIN_PCT = 80.0
WEAK_MAX_PCT = 70.0


def classify_topics(topic_df: pd.DataFrame, legacy_weak: list | None = None) -> dict:
    """
    จัดกลุ่มหัวข้อย่อยของวิชาเป็น strong / mid / weak จากผลสอบสะสมทุกครั้ง
    topic_df: คอลัมน์ ['topic', 'total', 'correct'] (หัวข้อเดียวกันซ้ำหลายแถวได้ จะรวมให้)
    legacy_weak: หัวข้อที่อ่อนจากการสอบรุ่นเก่าที่ยังไม่มีข้อมูลรายหัวข้อ
    """
    result = {"strong": [], "mid": [], "weak": []}
    seen = set()

    if topic_df is not None and not topic_df.empty:
        tmp = topic_df.copy()
        tmp["key"] = tmp["topic"].astype(str).str.strip().str.lower()
        agg = (
            tmp.groupby("key")
            .agg(topic=("topic", "first"), total=("total", "sum"), correct=("correct", "sum"))
            .reset_index()
        )
        agg = agg[agg["total"] > 0].copy()
        agg["pct"] = agg["correct"] / agg["total"] * 100

        for _, r in agg.sort_values("pct", ascending=False).iterrows():
            seen.add(r["key"])
            if r["pct"] >= STRONG_MIN_PCT:
                result["strong"].append(str(r["topic"]).strip())
            elif r["pct"] < WEAK_MAX_PCT:
                result["weak"].append(str(r["topic"]).strip())
            else:
                result["mid"].append(str(r["topic"]).strip())
        result["weak"].reverse()  # อ่อนที่สุดขึ้นก่อน

    for t in (legacy_weak or []):
        key = str(t).strip().lower()
        if key and key not in seen:
            seen.add(key)
            result["weak"].append(str(t).strip())

    return result