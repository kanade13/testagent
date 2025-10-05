FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# 让容器启动时执行 start_test.py
CMD ["python3", "start_test.py"]
