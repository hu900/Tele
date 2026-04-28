import io
import hashlib
import pdfplumber

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def is_valid_pdf_bytes(file_bytes: bytes) -> bool:
    return bool(file_bytes) and file_bytes.startswith(b"%PDF")

def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts).strip()
