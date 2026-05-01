import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_questions(text_content, count=5):
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # تحسين البرومبت للتركيز على الاختبارات السابقة
    prompt = f"""
    أنت محرك استخراج أسئلة. النص التالي مستخرج من "اختبار سابق".
    قم باستخراج {count} أسئلة اختيار من متعدد موجودة فعلياً في النص.
    
    القواعد:
    1. انقل السؤال والخيارات حرفياً كما وردت.
    2. تأكد من تحديد الإجابة الصحيحة (استنتجها إذا لم تكن معلمة في النص).
    3. إذا لم تجد أسئلة في النص، لا تؤلف من عندك، بل ارجع قائمة فارغة.
    4. أرجع الناتج بصيغة JSON حصراً.

    JSON Structure:
    {{
      "questions": [
        {{
          "question": "نص السؤال",
          "options": ["خيار 1", "خيار 2", "خيار 3", "خيار 4"],
          "answer": "النص المطابق للإجابة الصحيحة"
        }}
      ]
    }}

    Text Content:
    {text_content[:7000]}
    """

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": "You are a precise exam data extractor."},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("questions", [])
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return []
