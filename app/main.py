import os
import subprocess
import uuid
import xml.etree.ElementTree as ET
from fastapi import FastAPI, UploadFile, File, Request, StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
import json
from datetime import datetime, timedelta
import threading
import time

app = FastAPI()

# Favicon
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join('static', 'favicon.ico'))

# Directories for uploads and reports
UPLOAD_DIR = "/tmp/uploads"
REPORT_DIR = "/tmp/reports"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# Path to validator JAR and scenarios
VALIDATOR_JAR = "/app/validator.jar"
SCENARIOS_DIR = "/scenarios"

# Cleanup interval in seconds (10 minutes = 600 seconds)
CLEANUP_INTERVAL = 600

templates = Jinja2Templates(directory="templates")

# Cleanup thread as module-level variable
_cleanup_thread = None

def cleanup_old_files():
    """Cleanup old files periodically"""
    while True:
        try:
            now = datetime.now()
            
            # Clean up upload directory
            for filename in os.listdir(UPLOAD_DIR):
                filepath = os.path.join(UPLOAD_DIR, filename)
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if now - file_time > timedelta(seconds=CLEANUP_INTERVAL):
                        os.remove(filepath)
                        print(f"Cleaned up old upload file: {filename}")
                except Exception as e:
                    print(f"Error cleaning upload file {filename}: {e}")
            
            # Clean up report directory
            for filename in os.listdir(REPORT_DIR):
                filepath = os.path.join(REPORT_DIR, filename)
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if now - file_time > timedelta(seconds=CLEANUP_INTERVAL):
                        os.remove(filepath)
                        print(f"Cleaned up old report file: {filename}")
                except Exception as e:
                    print(f"Error cleaning report file {filename}: {e}")
            
        except Exception as e:
            print(f"Error in cleanup thread: {e}")
        
        # Sleep for 1 minute before next cleanup
        time.sleep(60)

def start_cleanup_thread():
    """Start the cleanup thread"""
    global _cleanup_thread
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
        _cleanup_thread.start()
        print("Cleanup thread started")
    return _cleanup_thread

# Start cleanup thread on module import
start_cleanup_thread()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def parse_xml_report(xml_path):
    """Parse the XML validation report and extract structured data with detailed classification."""
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
        valid_attr = root.get('valid', 'false').lower()
        valid = (valid_attr == 'true')
        
        # Extract timestamp
        timestamp_elem = root.find('rep:timestamp', namespaces)
        timestamp = timestamp_elem.text if timestamp_elem is not None else datetime.now().isoformat()
        
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
        
        # Extract assessment
        assessment_elem = root.find('.//rep:assessment', namespaces)
        accepted = False
        rejected = False
        if assessment_elem is not None:
            accepted = assessment_elem.find('rep:accept', namespaces) is not None
            rejected = assessment_elem.find('rep:reject', namespaces) is not None
        
        # Classify validation steps by severity
        validation_steps = []
        error_categories = {
            'schema': {'count': 0, 'messages': []},
            'schematron': {'count': 0, 'messages': []},
            'business_rules': {'count': 0, 'messages': []},
            'codelists': {'count': 0, 'messages': []},
            'syntax': {'count': 0, 'messages': []},
            'general': {'count': 0, 'messages': []}
        }
        
        # Message statistics - using original levels as they appear in XML
        message_stats = {
            'error': 0,
            'warning': 0,
            'info': 0,
            'information': 0,
            'fatal': 0
        }
        
        for step in root.findall('.//rep:validationStepResult', namespaces):
            step_id = step.get('id', 'unknown')
            step_valid = step.get('valid', 'false').lower() == 'true'
            
            resource_elem = step.find('s:resource/s:name', namespaces)
            resource_name = resource_elem.text if resource_elem is not None else 'Unknown'
            
            # Extract messages with their original levels
            messages = []
            for msg in step.findall('rep:message', namespaces):
                original_level = msg.get('level', 'info')
                # Keep original level as is
                msg_level = original_level
                msg_code = msg.get('code', '')
                msg_text = msg.text or ''
                
                # Count by original level
                if msg_level in message_stats:
                    message_stats[msg_level] += 1
                else:
                    # If unknown level, count as info
                    message_stats['info'] += 1
                
                # Categorize by error type
                error_type = categorize_error(msg_code, msg_text, resource_name)
                error_categories[error_type]['count'] += 1
                error_categories[error_type]['messages'].append({
                    'code': msg_code,
                    'text': msg_text,
                    'step': step_id,
                    'level': msg_level
                })
                
                messages.append({
                    'id': msg.get('id', ''),
                    'original_level': msg_level,  # Keep original level
                    'code': msg_code,
                    'line': msg.get('lineNumber', ''),
                    'column': msg.get('columnNumber', ''),
                    'text': msg_text,
                    'category': error_type
                })
            
            validation_steps.append({
                'id': step_id,
                'valid': step_valid,
                'resource': resource_name,
                'messages': messages
            })
        
        # Combine info and information counts for display
        total_info = message_stats.get('info', 0) + message_stats.get('information', 0)
        display_stats = {
            'error': message_stats.get('error', 0),
            'warning': message_stats.get('warning', 0),
            'info': total_info,
            'fatal': message_stats.get('fatal', 0)
        }
        
        # Determine overall status
        total_errors = display_stats['error'] + display_stats['fatal']
        total_warnings = display_stats['warning']
        
        if total_errors > 0:
            status = 'error'
            description = f'Das geprüfte Dokument enthält {total_errors} Fehler / {total_warnings} Warnungen. Es ist nicht konform zu den formalen Vorgaben.'
            recommendation = 'Es wird empfohlen das Dokument zurückzuweisen.'
        elif total_warnings > 0:
            status = 'warning'
            description = f'Validation passed with {total_warnings} warnings'
            recommendation = 'Document is compliant but contains warnings. Recommended for acceptance.'
        else:
            status = 'success'
            description = 'Das geprüfte Dokument enthält weder Fehler noch Warnungen. Es ist konform zu den formalen Vorgaben.'
            recommendation = 'Es wird empfohlen das Dokument anzunehmen und weiter zu verarbeiten.'
        
        return {
            'valid': valid,
            'status': status,
            'status_description': description,
            'recommendation': recommendation,
            'message_stats': display_stats,
            'original_message_stats': message_stats,  # Keep original for debugging
            'error_categories': error_categories,
            'timestamp': timestamp,
            'documentReference': doc_ref,
            'documentData': doc_data,
            'scenario': scenario_name,
            'validationSteps': validation_steps,
            'assessment': {'accepted': accepted, 'rejected': rejected}
        }
    except Exception as e:
        return {
            'valid': False,
            'status': 'fatal',
            'status_description': f'Error parsing report: {str(e)}',
            'recommendation': 'The document could not be processed.',
            'message_stats': {'error': 1, 'warning': 0, 'info': 0, 'fatal': 1},
            'error_categories': {},
            'timestamp': datetime.now().isoformat(),
            'documentReference': 'N/A',
            'documentData': {},
            'scenario': 'N/A',
            'validationSteps': [],
            'assessment': {'accepted': False, 'rejected': True}
        }

def categorize_error(code, text, resource):
    """Categorize error message based on code and text."""
    if not text:
        return 'general'
    
    text_lower = text.lower()
    
    # Schema validation errors
    if any(keyword in text_lower for keyword in ['schema', 'xsd', 'element', 'attribute', 'namespace']):
        return 'schema'
    
    # Schematron rule violations
    if any(keyword in text_lower for keyword in ['rule', 'assert', 'report', 'pattern']):
        return 'schematron'
    
    # Codelist errors
    if any(keyword in text_lower for keyword in ['codelist', 'code list', 'enumeration', 'invalid code']):
        return 'codelists'
    
    # Business rule violations
    if any(keyword in text_lower for keyword in ['business rule', 'calculation', 'total', 'amount', 'date']):
        return 'business_rules'
    
    # Syntax errors
    if any(keyword in text_lower for keyword in ['syntax', 'well-formed', 'parsing', 'malformed']):
        return 'syntax'
    
    return 'general'

@app.post("/validate", response_class=HTMLResponse)
async def validate(request: Request, file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    try:
        # Write uploaded file
        with open(input_path, "wb") as f:
            f.write(await file.read())
        
        
        # Generate unique report name
        unique_report_name = f"report_{file_id}.xml"
        report_path = os.path.join(REPORT_DIR, unique_report_name)

        # Execute validator
        cmd = [
            "java", "-jar", VALIDATOR_JAR,
            "-s", os.path.join(SCENARIOS_DIR, "scenarios.xml"),
            "-o", REPORT_DIR,
            "-n", unique_report_name,  # Die meisten Validator-JARs unterstützen -n für den Dateinamen
            input_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        success = result.returncode == 0
        
        # Find the generated report - XRechnung validator uses input filename for output
        report_path = None
        base_name = os.path.splitext(file.filename)[0]
        
        # Try different patterns for report file
        possible_patterns = [
            os.path.join(REPORT_DIR, f"{base_name}_report.xml"),
            os.path.join(REPORT_DIR, f"{base_name}.xml"),
            os.path.join(REPORT_DIR, f"report_{base_name}.xml"),
            os.path.join(REPORT_DIR, f"validation_report_{file_id}.xml")
        ]
        
        for pattern in possible_patterns:
            if os.path.exists(pattern):
                report_path = pattern
                break
        
        # If not found, look for any XML file containing the base name
        if report_path is None:
            for f in os.listdir(REPORT_DIR):
                if f.endswith('.xml') and (base_name in f or file_id in f):
                    report_path = os.path.join(REPORT_DIR, f)
                    break
        
        report_data = None
        if report_path and os.path.exists(report_path):
            report_data = parse_xml_report(report_path)
        else:
            # If no report found, create a basic one from validator output
            report_data = {
                'valid': success,
                'status': 'error' if not success else 'success',
                'status_description': 'Could not find validation report',
                'recommendation': 'Validator output available below',
                'message_stats': {'error': 0, 'warning': 0, 'info': 0, 'fatal': 0},
                'error_categories': {},
                'timestamp': datetime.now().isoformat(),
                'documentReference': file.filename,
                'documentData': {},
                'scenario': 'N/A',
                'validationSteps': [],
                'assessment': {'accepted': success, 'rejected': not success},
                'validator_output': result.stdout + result.stderr
            }
        
        return templates.TemplateResponse("result.html", {
            "request": request,
            "success": success,
            "report_data": json.dumps(report_data, ensure_ascii=False),
            "filename": file.filename,
            "file_id": file_id,
            "validator_output": result.stdout + result.stderr
        })
        
    except subprocess.TimeoutExpired:
        return templates.TemplateResponse("result.html", {
            "request": request,
            "success": False,
            "report_data": json.dumps({
                'valid': False,
                'status': 'fatal',
                'status_description': 'Validation timeout after 60 seconds',
                'recommendation': 'Document processing took too long',
                'message_stats': {'error': 0, 'warning': 0, 'info': 0, 'fatal': 1},
                'error_categories': {},
                'timestamp': datetime.now().isoformat(),
                'documentReference': file.filename,
                'documentData': {},
                'scenario': 'N/A',
                'validationSteps': [],
                'assessment': {'accepted': False, 'rejected': True}
            }, ensure_ascii=False),
            "filename": file.filename,
            "file_id": file_id,
            "validator_output": "Validation timeout after 60 seconds"
        })
    except Exception as e:
        return templates.TemplateResponse("result.html", {
            "request": request,
            "success": False,
            "report_data": json.dumps({
                'valid': False,
                'status': 'fatal',
                'status_description': f'Unexpected error: {str(e)}',
                'recommendation': 'System error occurred during validation',
                'message_stats': {'error': 1, 'warning': 0, 'info': 0, 'fatal': 0},
                'error_categories': {},
                'timestamp': datetime.now().isoformat(),
                'documentReference': file.filename,
                'documentData': {},
                'scenario': 'N/A',
                'validationSteps': [],
                'assessment': {'accepted': False, 'rejected': True}
            }, ensure_ascii=False),
            "filename": file.filename,
            "file_id": file_id,
            "validator_output": str(e)
        })
    finally:
        # Always delete the uploaded file immediately after processing
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
                print(f"Deleted uploaded file: {input_path}")
        except Exception as e:
            print(f"Error deleting uploaded file {input_path}: {e}")

@app.get("/download-report/{file_id}")
async def download_report(file_id: str):
    """Download the validation report as XML."""
    report_path = None
    for f in os.listdir(REPORT_DIR):
        if file_id in f and f.endswith('.xml'):
            report_path = os.path.join(REPORT_DIR, f)
            break
    
    if report_path and os.path.exists(report_path):
        # Update file timestamp to extend its life
        try:
            os.utime(report_path, None)
        except:
            pass
            
        return FileResponse(
            report_path,
            filename=f"validation_report_{file_id}.xml",
            media_type="application/xml"
        )
    
    return {"error": "Report not found or expired"}

@app.get("/cleanup")
async def manual_cleanup():
    """Manual cleanup endpoint for testing"""
    files_deleted = 0
    
    # Clean up upload directory
    for filename in os.listdir(UPLOAD_DIR):
        filepath = os.path.join(UPLOAD_DIR, filename)
        try:
            os.remove(filepath)
            files_deleted += 1
            print(f"Manually deleted: {filepath}")
        except Exception as e:
            print(f"Error deleting {filepath}: {e}")
    
    # Clean up report directory
    for filename in os.listdir(REPORT_DIR):
        filepath = os.path.join(REPORT_DIR, filename)
        try:
            os.remove(filepath)
            files_deleted += 1
            print(f"Manually deleted: {filepath}")
        except Exception as e:
            print(f"Error deleting {filepath}: {e}")
    
    return {"status": f"Deleted {files_deleted} files"}

@app.get("/health")
async def health():
    # Check if cleanup thread is still alive
    thread = start_cleanup_thread()
    
    if thread and thread.is_alive():
        return {"status": "alive", "cleanup_thread": "running"}
    else:
        # Try to restart cleanup thread
        start_cleanup_thread()
        return {"status": "alive", "cleanup_thread": "restarted"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)