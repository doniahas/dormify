FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt constraints.txt ./

RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]