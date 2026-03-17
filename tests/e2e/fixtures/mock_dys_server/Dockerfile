FROM python:3.11-slim

WORKDIR /app
RUN pip install fastapi uvicorn python-multipart
COPY main.py .

EXPOSE 8888
CMD ["python", "main.py"]
