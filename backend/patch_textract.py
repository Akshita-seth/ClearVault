new_function = '''
def extract_questions_from_s3(s3_key: str) -> list[dict]:
    logger.info(f"Extracting questions using PyPDF2 from s3://{S3_BUCKET}/{s3_key}")
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        pdf_bytes = obj["Body"].read()
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 read failed: {str(e)}")
    
    import PyPDF2
    import io
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    lines = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            lines.extend(text.split("\\n"))
    
    questions = []
    q_num = 1
    for line in lines:
        line = line.strip()
        is_question = (
            line.endswith("?")
            or (len(line) > 2 and line[0].isdigit() and (". " in line[:4] or ") " in line[:4]))
        )
        if is_question and len(line) > 10:
            questions.append({"question_id": f"Q-{str(q_num).zfill(3)}", "question_text": line})
            q_num += 1
    
    logger.info(f"Extracted {len(questions)} questions")
    return questions
'''

with open("main.py", "r") as f:
    content = f.read()

start = content.index("def extract_questions_from_s3")
end = content.index("\ndef query_knowledge_base")
content = content[:start] + new_function.strip() + "\n" + content[end:]

with open("main.py", "w") as f:
    f.write(content)

print("Done! Textract replaced with PyPDF2.")
