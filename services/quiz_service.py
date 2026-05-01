import os
import json
from openai import OpenAI

# يتم جلب المفتاح تلقائياً من إعدادات Railway
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def get_exam_questions(text_content, count=10):
    """
    استخراج الأسئلة الفعلية من نص الاختبار السابق باستخدام OpenAI.
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # تحديد كمية النص لضمان عدم تجاوز الـ Tokens (أول 5000 حرف غالباً تكفي لعدة أسئلة)
    context = text_content[:6000]

    prompt = f"""
    أنت متخصص في تحليل أوراق الاختبارات. 
    المهمة: استخرج {count} أسئلة من النص المرفق وهو عبارة عن "اختبار سابق".
    
    التعليمات الصارمة:
    1. استخرج الأسئلة *كما وردت* في النص دون تأليف أسئلة جديدة.
    2. يجب أن يكون السؤال من نوع "اختيار من متعدد" وله 4 خيارات.
    3. استخرج الإجابة الصحيحة إذا كانت محددة في النص، أو استنتجها إذا كانت غائبة.
    4. الناتج يجب أن يكون JSON فقط وبنفس لغة النص الأصلي.

    التنسيق المطلوب:
    {{
      "questions": [
        {{
          "question": "نص السؤال المستخرج",
          "options": ["خيار 1", "خيار 2", "خيار 3", "خيار 4"],
          "answer": "نص الإجابة الصحيحة المطابق تماماً لأحد الخيارات"
        }}
      ]
    }}

    النص:
    {context}
    """

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a precise exam extractor. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1 # درجة حرارة منخفضة جداً لضمان النقل الحرفي وعدم الإبداع
        )

        raw_data = json.loads(response.choices[0].message.content)
        return raw_data.get("questions", [])
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return []
