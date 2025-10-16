FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source code
COPY frontend/ .

# Expose port (Reflex default is 3000)
EXPOSE 3000

# Default command
CMD ["reflex", "run", "--env", "prod"]