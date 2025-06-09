FROM python:3.12-slim

RUN pip install --no-cache-dir TikTokApi

COPY get_token.py .

ENTRYPOINT ["python", "-u", "get_token.py"]
