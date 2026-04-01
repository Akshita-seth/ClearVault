"""
ClearVault — FastAPI Backend
Team: Null Hypothesis | Hack'A'War GenAI × AWS
"""

import os
import uuid
import time
import logging
from typing import Optional
import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

AWS_REGION          = "us-east-1"
S3_BUCKET           = "clearvault-policies"
KNOWLEDGE_BASE_ID   = "HFXDFMGFCK"
DATA_SOURCE_ID      = "ZQOMCNK8V1"
MODEL_ARN           = "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
QUESTIONNAIRE_PREFIX = "questionnaires/"
POLICIES_PREFIX      = "policies/"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clearvault")

s3            = boto3.client("s3", region_name=AWS_REGION)
textract      = boto3.client("textract", region_name=AWS_REGION)
bedrock       = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
bedrock_agent = boto3.client("bedrock-agent", region_name=AWS_REGION)

app = FastAPI(title="ClearVault API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnswerItem(BaseModel):
    question_id: str
    question_text: str
    answer: str
    confidence: float
    confidence_label: str
    source: str
    flagged: bool

class QuestionnaireResponse(BaseModel):
    answers: list[AnswerItem]
    total: int
    auto_answered: int
    flagged_count: int

class UploadResponse(BaseModel):
    status: str
    doc_count: int
    message: str

def calculate_confidence(answer: str, sources: list) -> dict:
    if len(sources) == 0:
        score = 0.2
    elif len(sources) == 1:
        score = 0.65
    else:
        score = 0.85
    vague_phrases = [
        "i don't know", "no information", "not mentioned",
        "unclear", "cannot find", "not found", "no relevant",
        "no specific", "i cannot", "not available"
    ]
    if any(phrase in answer.lower() for phrase in vague_phrases):
        score -= 0.3
    if len(answer) > 100 and score < 0.85:
        score += 0.05
    score = round(max(0.0, min(1.0, score)), 2)
    if score >= 0.80:
        label = "HIGH"
    elif score >= 0.50:
        label = "MEDIUM"
    else:
        label = "LOW"
    return {"confidence": score, "confidence_label": label, "flagged": score < 0.50}

def extract_source(citations: list) -> str:
    try:
        for citation in citations:
            refs = citation.get("retrievedReferences", [])
            for ref in refs:
                loc = ref.get("location", {})
                uri = loc.get("s3Location", {}).get("uri", "")
                if uri:
                    filename = uri.split("/")[-1].replace(".pdf", "").replace("_", " ")
                    return filename
    except Exception:
        pass
    return "Policy Documents"

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
            lines.extend(text.split("\n"))
    
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

def query_knowledge_base(question: str) -> dict:
    import boto3
    from groq import Groq
    import os
    try:
        bedrock_retrieval = boto3.client("bedrock-agent-runtime", region_name="us-east-1")
        retrieval_response = bedrock_retrieval.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": question},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}}
        )
        results = retrieval_response.get("retrievalResults", [])
        context = "\n\n".join([r["content"]["text"] for r in results])
        sources = results
    except Exception as e:
        logger.warning(f"KB retrieval failed: {e}")
        context = "No context available."
        sources = []
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": f"You are a security compliance expert. Answer this security questionnaire question based ONLY on the provided policy documents. Be specific and concise (2-4 sentences). If not in documents, say so clearly.\n\nQuestion: {question}\n\nPolicy context:\n{context}"}],
            max_tokens=300
        )
        answer = response.choices[0].message.content
        return {"answer": answer, "sources": sources}
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return {"answer": "Unable to generate answer.", "sources": []}

def trigger_kb_sync():
    try:
        bedrock_agent.start_ingestion_job(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            dataSourceId=DATA_SOURCE_ID,
        )
        logger.info("KB sync triggered")
    except ClientError as e:
        logger.warning(f"KB sync warning: {e}")

@app.get("/health")
def health():
    return {"status": "ok", "service": "ClearVault API", "version": "1.0.0", "kb_id": KNOWLEDGE_BASE_ID}

@app.post("/upload-policies", response_model=UploadResponse)
async def upload_policies(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    uploaded = 0
    errors = []
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            errors.append(f"{f.filename}: only PDF files accepted")
            continue
        try:
            content = await f.read()
            s3_key = f"{POLICIES_PREFIX}{uuid.uuid4()}_{f.filename}"
            s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=content, ContentType="application/pdf")
            logger.info(f"Uploaded: {s3_key}")
            uploaded += 1
        except ClientError as e:
            errors.append(f"{f.filename}: {e}")
    if uploaded == 0:
        raise HTTPException(status_code=500, detail=f"All uploads failed: {errors}")
    trigger_kb_sync()
    return UploadResponse(
        status="indexed",
        doc_count=uploaded,
        message=f"Uploaded {uploaded} document(s). KB sync started." + (f" Warnings: {errors}" if errors else "")
    )

@app.post("/process-questionnaire", response_model=QuestionnaireResponse)
async def process_questionnaire(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted")
    content = await file.read()
    s3_key = f"{QUESTIONNAIRE_PREFIX}{uuid.uuid4()}_{file.filename}"
    try:
        s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=content, ContentType="application/pdf")
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")
    questions = extract_questions_from_s3(s3_key)
    if not questions:
        raise HTTPException(status_code=422, detail="No questions could be extracted from this PDF.")
    answers = []
    for q in questions:
        logger.info(f"Processing {q['question_id']}: {q['question_text'][:60]}...")
        rag_result = query_knowledge_base(q["question_text"])
        confidence_result = calculate_confidence(rag_result["answer"], rag_result["sources"])
        source = extract_source(rag_result["sources"])
        answers.append(AnswerItem(
            question_id=q["question_id"],
            question_text=q["question_text"],
            answer=rag_result["answer"],
            confidence=confidence_result["confidence"],
            confidence_label=confidence_result["confidence_label"],
            source=source,
            flagged=confidence_result["flagged"],
        ))
        time.sleep(0.3)
    flagged_count = sum(1 for a in answers if a.flagged)
    return QuestionnaireResponse(
        answers=answers,
        total=len(answers),
        auto_answered=len(answers) - flagged_count,
        flagged_count=flagged_count,
    )
