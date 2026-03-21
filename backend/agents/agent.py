import os
from openai import OpenAI

from dotenv import load_dotenv
load_dotenv()

def _get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    _client = OpenAI(api_key=api_key)
    return _client

def generate(prompt, context):
    client = _get_openai_client()
    messages = [
        {"role": "system", "content": context},
        {"role": "user", "content": prompt},
    ]
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return ''