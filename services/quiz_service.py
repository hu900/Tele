import json
import random
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_FALLBACK_MODEL, MAX_CHUNK_TEXT_CHARS

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def _chunk_block_ar(chunks):
    sections = []
    for i, ch in enumerate(chunks, start=1):
        keywords = "، ".join(ch.get("keywords", []))
        points = "\n".join([f"- {p}" for p in ch.get("learning_points", [])])
        text = ch["chunk_text"][:MAX_CHUNK_TEXT_CHARS]

        sections.append(
            f"""[المقطع {i}]
الكلمات المفتاحية: {keywords}
نقاط التعلم:
{points if points else "- لا يوجد"}

النص:
{text}"""
        )
    return "\n\n".join(sections)

def _chunk_block_en(chunks):
    sections = []
    for i, ch in enumerate(chunks, start=1):
        keywords = ", ".join(ch.get("keywords", []))
        points = "\n".join([f"- {p}" for p in ch.get("learning_points", [])])
        text = ch["chunk_text"][:MAX_CHUNK_TEXT_CHARS]

        sections.append(
            f"""[Chunk {i}]
Keywords: {keywords}
Learning points:
{points if points else "- None"}

Text:
{text}"""
        )
    return "\n\n".join(sections)

def build_prompt(chunks, num_q, language):
    if language == "arabic":
        return f"""
أنت خبير تعليمي. أمامك عدة مقاطع من نفس الملف، ومع كل مقطع كلمات مفتاحية ونقاط تعلم.
أنشئ {num_q} أسئلة اختيار من متعدد بصيغة JSON فقط.
لغة الأسئلة والخيارات والإجابات يجب أن تكون العربية.
احرص على التنوع وعدم تكرار الفكرة نفسها.
وزّع الأسئلة على المقاطع المتاحة قدر الإمكان.

أعد النتيجة بصيغة JSON فقط بهذا الشكل:
{{
  "questions": [
    {{
      "question": "نص السؤال",
      "options": ["الخيار 1", "الخيار 2", "الخيار 3", "الخيار 4"],
      "answer": "الخيار الصحيح كما هو حرفياً"
    }}
  ]
}}

شروط مهمة:
- كل سؤال يجب أن يحتوي 4 خيارات بالضبط.
- answer يجب أن يطابق أحد الخيارات حرفياً.
- لا تضف أي نص خارج JSON.
- اجعل الأسئلة واضحة ومباشرة ومناسبة للمحتوى.
- لا تكرر سؤالاً أو فكرةً مكررة بشكل واضح.

المقاطع:
{_chunk_block_ar(chunks)}
"""
    return f"""
You are an educational expert. You are given multiple chunks from the same document,
along with keywords and learning points for each chunk.
Generate {num_q} multiple-choice questions in English only.
Ensure variety and avoid repeating the same idea.
Distribute questions across the available chunks as much as possible.

Return JSON only in this exact format:
{{
  "questions": [
    {{
      "question": "Question text",
      "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
      "answer": "The correct option exactly as written"
    }}
  ]
}}

Important rules:
- Each question must have exactly 4 options.
- The answer must exactly match one option.
- Do not output anything outside JSON.
- Make questions clear and directly grounded in the chunks.
- Avoid near-duplicate questions.

Chunks:
{_chunk_block_en(chunks)}
"""

def _call_openai_json(prompt, model_name):
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a helpful assistant designed to output JSON only."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
    )
    return response.choices[0].message.content

def _parse_questions(raw_content):
    data = json.loads(raw_content)
    raw_questions = data.get("questions", [])
    valid_questions = []
    seen = set()

    for q in raw_questions:
        question = str(q.get("question", "")).strip()
        options = [str(opt).strip() for opt in q.get("options", []) if str(opt).strip()]
        answer = str(q.get("answer", "")).strip()

        key = question.lower()
        if not question or key in seen:
            continue
        if len(options) != 4:
            continue
        if answer not in options:
            continue

        seen.add(key)
        valid_questions.append({
            "question": question,
            "options": options,
            "answer": answer
        })

    random.shuffle(valid_questions)
    return valid_questions

def generate_quiz_from_chunks(chunks, num_q=5, language="arabic"):
    if not client or not chunks:
        return []

    prompt = build_prompt(chunks, num_q, language)
    models_to_try = [OPENAI_MODEL]
    if OPENAI_FALLBACK_MODEL and OPENAI_FALLBACK_MODEL != OPENAI_MODEL:
        models_to_try.append(OPENAI_FALLBACK_MODEL)

    for model_name in models_to_try:
        try:
            content = _call_openai_json(prompt, model_name)
            questions = _parse_questions(content)
            if questions:
                return questions[:num_q]
        except Exception:
            continue

    return []
