new_function = '''
def query_knowledge_base(question: str) -> dict:
    import anthropic
    import boto3
    
    # Step 1: Retrieve relevant docs from Bedrock KB
    bedrock_retrieval = boto3.client("bedrock-agent-runtime", region_name="us-east-1")
    try:
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
    
    # Step 2: Generate answer using Anthropic directly
    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=512,
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
            }]
        )
        answer = message.content[0].text
        return {"answer": answer, "sources": sources}
    except Exception as e:
        logger.error(f"Anthropic error: {e}")
        return {"answer": "Unable to generate answer.", "sources": []}
'''

with open("main.py", "r") as f:
    content = f.read()

start = content.index("def query_knowledge_base")
end = content.index("\ndef trigger_kb_sync")
content = content[:start] + new_function.strip() + "\n" + content[end:]

with open("main.py", "w") as f:
    f.write(content)

print("Done! Bedrock replaced with Anthropic Direct API.")
