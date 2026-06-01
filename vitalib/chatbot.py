import os
from openai import OpenAI
from google import genai


class Chatbot:
    class OpenAI:
        def __init__(self, model):
            self.model = model
            self.client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

        def send_message(self, message):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": message}
                ],
            )
            return response.choices[0].message.content


    class Gemini:
        def __init__(self, model):
            self.model = model
            self.client = genai.Client(api_key=os.getenv("GEMINI_KEY"))

        def send_message(self, message):
            response = self.client.models.generate_content(
                model=self.model,
                contents=message,
            )
            return response.text