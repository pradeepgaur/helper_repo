import openai

client = openai.AzureOpenAI(
    azure_endpoint="https://<your-resource>.openai.azure.com/",
    api_key="<your-key>",
    api_version="2024-02-01"
)

response = client.chat.completions.create(
    model="<your-deployment-name>",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain gravity in one sentence."}
    ],
    temperature=0,
    seed=42,
    top_p=1
)

print(response.choices[0].message.content)

# Check if system fingerprint changed (see below)
print(response.system_fingerprint)
