FROM mcr.microsoft.com/playwright/python:v1.51.0-noble

# Set working directory
# WORKDIR /app
# RUN chown -R 1000:1000 /app

# Install python dependencies
RUN pip install --no-cache-dir TikTokApi
# RUN python -m playwright install
RUN playwright install chromium

RUN apt update && apt install xvfb -y
# Copy application code
COPY entrypoint.sh .
COPY get_token_xvfb.py .


# Run the cron daemon as the entrypoint
# ENTRYPOINT ["python3", "-u", "get_token_xvfb.py"]
# ENTRYPOINT ["xvfb-run", "python3", "/app/get_token_xvfb.py"]
ENTRYPOINT ["/bin/sh", "entrypoint.sh"]
