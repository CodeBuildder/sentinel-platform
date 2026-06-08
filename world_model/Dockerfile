FROM python:3.12-slim

WORKDIR /app

# install deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy the shared SDK and schemas from the repo root
COPY ../sentinel_sdk /app/sentinel_sdk
COPY ../schemas /app/schemas

COPY src/ /app/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
