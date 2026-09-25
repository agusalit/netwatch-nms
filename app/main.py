from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Initialize FastAPI app
app = FastAPI(title="Monitoring App")

# Wire up Jinja2 templates directory
templates = Jinja2Templates(directory="app/templates")


# 1. Health endpoint (used by external tools or monitoring to verify app is alive)
@app.get("/health")
def health_check():
    return {"status": "ok"}


# 2. Main dashboard page rendering the Jinja2 template
@app.get("/", response_class=HTMLResponse)
def read_dashboard(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={}  
    )
