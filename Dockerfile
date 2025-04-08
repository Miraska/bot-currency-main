FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libstdc++6 \
    libc6

RUN pip install playwright
RUN playwright install

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]


