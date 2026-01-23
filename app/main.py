import os
import subprocess
import uuid
import xml.etree.ElementTree as ET
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json

app = FastAPI()

# Verzeichnisse für Uploads und Reports
UPLOAD_DIR = "/tmp/uploads"
REPORT_DIR = "/tmp/reports"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# Pfad zum Validator JAR und Scenarios
VALIDATOR_JAR = "/home/ubuntu/xrechnung-validator/app/validator.jar"
SCENARIOS_DIR = "/home/ubuntu/xrechnung-validator/scenarios"

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def parse_xml_report(xml_path):
    """Parse the XML validation report and extract structured data."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Define namespaces
        namespaces = {
            'rep': 'http://www.xoev.de/de/validator/varl/1',
            's': 'http://www.xoev.de/de/validator/framework/1/scenarios',
            'html': 'http://www.w3.org/1999/xhtml',
            'ram': 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100',
            'rsm': 'urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100',
            'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
        }
        
        # Extract overall validity
        valid = root.get('valid', 'false').lower() == 'true'
        
        # Extract timestamp
        timestamp_elem = root.find('rep:timestamp', namespaces)
        timestamp = timestamp_elem.text if timestamp_elem is not None else 'N/A'
        
        # Extract document reference
        doc_ref_elem = root.find('.//rep:documentReference', namespaces)
        doc_ref = doc_ref_elem.text if doc_ref_elem is not None else 'N/A'
        
        # Extract document data
        doc_data = {}
        doc_data_elem = root.find('.//rep:documentData', namespaces)
        if doc_data_elem is not None:
            seller = doc_data_elem.find('seller', namespaces)
            doc_data['seller'] = seller.text if seller is not None else 'N/A'
            
            doc_id = doc_data_elem.find('id', namespaces)
            doc_data['id'] = doc_id.text if doc_id is not None else 'N/A'
            
            issue_date = doc_data_elem.find('issueDate', namespaces)
            doc_data['issueDate'] = issue_date.text if issue_date is not None else 'N/A'
        
        # Extract scenario info
        scenario_name = 'N/A'
        scenario_elem = root.find('.//s:scenario/s:name', namespaces)
        if scenario_elem is not None:
            scenario_name = scenario_elem.text
        
        # Extract validation step results
        validation_steps = []
        for step in root.findall('.//rep:validationStepResult', namespaces):
            step_id = step.get('id', 'unknown')
            step_valid = step.get('valid', 'false').lower() == 'true'
            
            resource_elem = step.find('s:resource/s:name', namespaces)
            resource_name = resource_elem.text if resource_elem is not None else 'Unknown'
            
            # Extract messages
            messages = []
            for msg in step.findall('rep:message', namespaces):
                messages.append({
                    'id': msg.get('id', ''),
                    'level': msg.get('level', 'info'),
                    'code': msg.get('code', ''),
                    'line': msg.get('lineNumber', ''),
                    'column': msg.get('columnNumber', ''),
                    'text': msg.text or ''
                })
            
            validation_steps.append({
                'id': step_id,
                'valid': step_valid,
                'resource': resource_name,
                'messages': messages
            })
        
        # Extract assessment
        assessment = {
            'accepted': root.find('.//rep:assessment/rep:accept', namespaces) is not None,
            'rejected': root.find('.//rep:assessment/rep:reject', namespaces) is not None
        }
        
        return {
            'valid': valid,
            'timestamp': timestamp,
            'documentReference': doc_ref,
            'documentData': doc_data,
            'scenario': scenario_name,
            'validationSteps': validation_steps,
            'assessment': assessment
        }
    except Exception as e:
        return {
            'valid': False,
            'error': str(e),
            'timestamp': 'N/A',
            'documentReference': 'N/A',
            'documentData': {},
            'scenario': 'N/A',
            'validationSteps': [],
            'assessment': {'accepted': False, 'rejected': True}
        }

@app.post("/validate", response_class=HTMLResponse)
async def validate(request: Request, file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    report_path = os.path.join(REPORT_DIR, f"{file_id}_report.xml")
    
    with open(input_path, "wb") as f:
        f.write(await file.read())
    
    # Validator ausführen
    cmd = [
        "java", "-jar", VALIDATOR_JAR,
        "-s", os.path.join(SCENARIOS_DIR, "scenarios.xml"),
        "-o", REPORT_DIR,
        input_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        success = result.returncode == 0
        
        # Parse the generated report
        report_data = None
        if os.path.exists(report_path):
            report_data = parse_xml_report(report_path)
        else:
            # Try to find the report with a different naming pattern
            for f in os.listdir(REPORT_DIR):
                if file_id in f and f.endswith('.xml'):
                    report_data = parse_xml_report(os.path.join(REPORT_DIR, f))
                    break
        
        if report_data is None:
            report_data = {
                'valid': success,
                'error': result.stdout + result.stderr,
                'timestamp': 'N/A',
                'documentReference': file.filename,
                'documentData': {},
                'scenario': 'N/A',
                'validationSteps': [],
                'assessment': {'accepted': success, 'rejected': not success}
            }
        
        return templates.TemplateResponse("result.html", {
            "request": request,
            "success": success,
            "report_data": json.dumps(report_data),
            "filename": file.filename,
            "file_id": file_id
        })
    except subprocess.TimeoutExpired:
        return templates.TemplateResponse("result.html", {
            "request": request,
            "success": False,
            "report_data": json.dumps({
                'valid': False,
                'error': 'Validation timeout after 60 seconds',
                'timestamp': 'N/A',
                'documentReference': file.filename,
                'documentData': {},
                'scenario': 'N/A',
                'validationSteps': [],
                'assessment': {'accepted': False, 'rejected': True}
            }),
            "filename": file.filename,
            "file_id": file_id
        })
    except Exception as e:
        return templates.TemplateResponse("result.html", {
            "request": request,
            "success": False,
            "report_data": json.dumps({
                'valid': False,
                'error': str(e),
                'timestamp': 'N/A',
                'documentReference': file.filename,
                'documentData': {},
                'scenario': 'N/A',
                'validationSteps': [],
                'assessment': {'accepted': False, 'rejected': True}
            }),
            "filename": file.filename,
            "file_id": file_id
        })

@app.get("/download-report/{file_id}")
async def download_report(file_id: str):
    """Download the validation report as XML."""
    report_path = None
    for f in os.listdir(REPORT_DIR):
        if file_id in f and f.endswith('.xml'):
            report_path = os.path.join(REPORT_DIR, f)
            break
    
    if report_path and os.path.exists(report_path):
        return FileResponse(
            report_path,
            filename=f"validation_report_{file_id}.xml",
            media_type="application/xml"
        )
    
    return {"error": "Report not found"}

@app.get("/health")
async def health():
    return {"status": "alive"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
