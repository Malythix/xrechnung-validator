import os
import subprocess
import uuid
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

# Verzeichnisse für Uploads und Reports
UPLOAD_DIR = "/tmp/uploads"
REPORT_DIR = "/tmp/reports"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# Pfad zum Validator JAR und Scenarios
VALIDATOR_JAR = "/app/validator.jar"
SCENARIOS_DIR = "/scenarios"

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/validate", response_class=HTMLResponse)
async def validate(request: Request, file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    report_path = os.path.join(REPORT_DIR, f"{file_id}_report.xml")
    
    with open(input_path, "wb") as f:
        f.write(await file.read())
    
    # Validator ausführen
    # Hinweis: Wir nutzen den CLI-Modus für Einfachheit (Quick & Dirty)
    # Falls keine Scenarios gemountet sind, wird der Validator einen Fehler werfen
    cmd = [
        "java", "-jar", VALIDATOR_JAR,
        "-s", os.path.join(SCENARIOS_DIR, "scenarios.xml"),
        "-o", REPORT_DIR,
        input_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        success = result.returncode == 0
        output = result.stdout + result.stderr
        
        # Suche nach dem generierten Report (der Validator benennt ihn oft nach dem Input)
        # In einer echten App müsste man das präziser handhaben
        return templates.TemplateResponse("result.html", {
            "request": request,
            "success": success,
            "output": output,
            "filename": file.filename
        })
    except Exception as e:
        return templates.TemplateResponse("result.html", {
            "request": request,
            "success": False,
            "output": str(e),
            "filename": file.filename
        })

@app.get("/health")
async def health():
    return {"status": "alive"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
