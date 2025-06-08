FROM python:3.12-slim
RUN apt-get update && apt-get install -y git && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir git+https://github.com/Egorrko/TikTok-Api.git@main

COPY get_token.py .

ENTRYPOINT ["python", "-u", "get_token.py"]
