# Nutze ein JRE-Image als Basis, da wir Java für den Validator brauchen
FROM eclipse-temurin:17-jre-focal

# Installiere Python und Pip
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis
WORKDIR /app

# Kopiere App-Dateien
COPY app/ /app/
COPY app/validator.jar /app/validator.jar

# Installiere Python-Abhängigkeiten
RUN pip3 install fastapi uvicorn jinja2 python-multipart

# Verzeichnisse für Validator
RUN mkdir -p /scenarios /tmp/uploads /tmp/reports

# Exponiere Port
EXPOSE 8080

# Startbefehl
CMD ["python3", "main.py"]
