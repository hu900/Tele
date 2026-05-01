import openai
import json
from config import OPENAI_API_KEY, OPENAI_MODEL

openai.api_key = OPENAI_API_KEY

async def extract_questions_from_text(text):
    """
    وظيفة هذا الجزء هي تحليل النص المستخرج من الـ PDF 
    وتحويل الأسئلة الموجودة فيه إلى صيغة برمجية
    """
    prompt = f"""
    أنت خبير في تحليل الاختبارات. مهمتك هي استخراج الأسئلة الموجودة في النص التالي وتحويلها إلى تنسيق JSON.
    
    النص مأخوذ من ملف اختبار سابق. قم باستخراج الأسئلة التي لها خيارات (A, B, C, D) فقط.
    
    شروط هامة:
    1. إذا كانت الإجابة الصحيحة مشار إليها في النص (مثلاً تحتها خط أو بجانبها علامة)، استخرجها.
    2. إذا لم تكن الإجابة موجودة، حاول استنتاج الإجابة الصحيحة بناءً على خبرتك.
    3. يجب أن يكون الناتج JSON فقط بهذا الشكل:
    {{
      "questions": [
        {{
          "question": "نص السؤال هنا",
          "options": ["الخيار الأول", "الخيار الثاني", "الخيار الثالث", "الخيار الرابع"],
          "answer": "نص الخيار الصحيح حرفياً"
        }}
      ]
    }}

    النص:
    {text}
    """

    try:
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": "You are a professional exam parser."},
                      {"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        data = json.loads(response.choices[0].message.content)
        return data.get('questions', [])
    except Exception as e:
        print(f"Error in AI Service: {e}")
        return []
