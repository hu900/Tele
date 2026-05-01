import pdfplumber
import io

def extract_text_from_pdf(file_bytes):
    """استخراج النص من ملف PDF مع تنظيف بسيط"""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return ""
