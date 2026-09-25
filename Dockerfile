# 1. Use the Python 3.11 slim base image
FROM python:3.11-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Environment variables to optimize Python for Docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 4. Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the entire application into the container
COPY . .

# 6. Expose port 8000
EXPOSE 8000

# 7. Start Uvicorn bound to 0.0.0.0
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
