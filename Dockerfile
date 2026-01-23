# Get JRE-Image as basis to use Validator.jar
FROM eclipse-temurin:17-jre-focal

# Install Python und Pip
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

# Work directory
WORKDIR /app

# Copy app data
COPY app/ /app/
COPY app/validator.jar /app/validator.jar

# Install Python dependencies
RUN pip3 install fastapi uvicorn jinja2 python-multipart

# Validator directories
RUN mkdir -p /scenarios /tmp/uploads /tmp/reports

# Expose port
EXPOSE 8080

# Start command
CMD ["python3", "main.py"]
