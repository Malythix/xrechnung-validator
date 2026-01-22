# KOSIT Validator Service

A minimalistic HTTP web service integrating the KOSIT Validator. Licensed under **Apache License 2.0**.

---

## Features

- Minimalistic frontend, providing a clean interface for uploading and validating XRechnung documents.  
- HTTP web service implemented with **FastAPI**, designed for efficiency and easy integration with other services.  
- Fully **Docker-ready** with `docker-compose.yml` for simple deployment and scaling.  
- **Traefik-compatible**, including support for labels, networks, and healthchecks, enabling seamless integration into existing reverse-proxy setups.  
- Supports multiple **validation scenarios** provided by KOSIT (e.g., UBL Invoice, CII, Extensions).  
- Modular structure allows easy extension or replacement of the frontend, API endpoints, or validation logic.  

---

## Quickstart

1. Extract the ZIP archive of the project to a suitable location.  
2. There are already the official scenarios present, but if you want other scenarios or customize them, replace your KOSIT Validator scenario files (e.g., `scenarios.xml` and any required XSD/XSLT files) into the folder `./scenarios`. These files define the validation rules for different XRechnung versions and document types.  
3. Build and start the service with Docker Compose:

   ```bash
   docker compose up -d --build
   ```

   This will build the FastAPI wrapper, start the KOSIT Validator container, and set up the internal network for communication.  

4. The service will be accessible at:
   ```bash
   http://localhost:8080
   ```
   You can now upload XRechnung XML files via the frontend or POST them to the `/validate` endpoint for automated validation.

---

## Directory Structure

- `app/`: Contains all Python code for the FastAPI wrapper and the minimalistic frontend, including endpoints for file upload, validation, and status reporting.
- `scenarios/`: Directory for all KOSIT configuration files (XML/XSD/XSLT) that define validation scenarios. This folder must be populated for the validator to work correctly.
- `Dockerfile`: Instructions for building the Docker image for the wrapper service. Ensures that the FastAPI server and all dependencies are installed.
- `docker-compose.yml`: Defines the service orchestration, including the validator container, wrapper service, network configuration, and Traefik labels.

## Additional Notes

- The service is **Apache License 2.0** compatible. The wrapper you create around the validator can also be licensed under Apache 2.0 or a compatible license, while the original KOSIT Validator remains under Apache 2.0.
- Designed for **headless operation** in automated pipelines, but can also serve browser-based uploads securely through Traefik and Keycloak authentication.
- Provides a foundation for **integration with Paperless-ngx**, automated batch validation, or other enterprise workflows.
- Healthcheck endpoints are included for Traefik to monitor container readiness and ensure that services remain routable and protected.