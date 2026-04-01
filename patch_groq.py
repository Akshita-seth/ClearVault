new_function = '''
def query_knowledge_base(question: str) -> dict:
    import boto3
    from groq import Groq
    import os

    # Step 1: Retrieve from Bedrock KB
    try:
        bedrock_retrieval = boto3.client("bedrock-agent-runtime", region_name="us-east-1")
        retrieval_response = bedrock_retrieval.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": question},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}}
        )
        results = retrieval_response.get("retrievalResults", [])
        context = "\\n\\n".join([r["content"]["text"] for r in results])
        sources = results
    except Exception as e:
        logger.warning(f"KB retrieval failed: {e}")
        context = "No context available."
        sources = []

    # Step 2: Generate answer using Groq
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{
                "role": "user",
                "content": (
                    f"You are a security compliance expert. "
                    f"Answer the following security questionnaire question "
                    f"based ONLY on the provided policy documents. "
                    f"Be specific and concise (2-4 sentences). "
                    f"If the information is not in the documents, say so clearly.\\n\\n"
                    f"Question: {question}\\n\\n"
                    f"Policy context:\\n{context}"
                )
            }],
            max_tokens=300
        )
        answer = response.choices[0].message.content
        return {"answer": answer, "sources": sources}
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return {"answer": "Unable to generate answer.", "sources": []}
'''

with open("main.py", "r") as f:
    content = f.read()

start = content.index("def query_knowledge_base")
end = content.index("\ndef trigger_kb_sync")
content = content[:start] + new_function.strip() + "\n" + content[end:]

with open("main.py", "w") as f:
    f.write(content)

print("Done! Groq patched in successfully.")
