# Use a lightweight python image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port (default is 8000, can be overridden by environment variable)
EXPOSE 8000

# Start application using uvicorn, expanding PORT env variable if present
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
