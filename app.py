import os
import uuid
import time
import zipfile
import shutil
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from converter import convert_file

app = FastAPI(title="Book2MD")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Store conversion tasks
tasks: dict = {}
executor = ThreadPoolExecutor(max_workers=4)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    task_ids = []

    for file in files:
        ext = Path(file.filename).suffix.lower()
        supported = {".pdf", ".epub", ".mobi", ".azw", ".azw3", ".kfx", ".djvu", ".fb2", ".cbz", ".cbr", ".xml", ".enex", ".notes"}
        if ext not in supported:
            continue

        task_id = str(uuid.uuid4())[:8]
        task_dir = UPLOAD_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        input_path = task_dir / file.filename
        content = await file.read()
        with open(input_path, "wb") as f:
            f.write(content)

        file_size = len(content)
        tasks[task_id] = {
            "filename": file.filename,
            "file_size": file_size,
            "status": "converting",
            "progress": 0,
            "total": 0,
            "result_path": None,
            "error": None,
            "duration": None,
            "start_time": time.time(),
        }

        executor.submit(_do_convert, task_id, str(input_path))
        task_ids.append(task_id)

    return {"task_ids": task_ids}


def _do_convert(task_id: str, input_path: str):
    import traceback
    logger = logging.getLogger(__name__)

    def on_progress(current, total):
        tasks[task_id]["progress"] = current
        tasks[task_id]["total"] = total

    try:
        logger.info(f"Starting conversion: {input_path}")
        md_text = convert_file(input_path, progress_cb=on_progress)
        md_filename = Path(input_path).stem + ".md"
        md_path = Path(input_path).parent / md_filename
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        tasks[task_id]["status"] = "done"
        tasks[task_id]["result_path"] = str(md_path)
        tasks[task_id]["duration"] = round(time.time() - tasks[task_id]["start_time"], 1)
        logger.info(f"Conversion done: {md_filename} in {tasks[task_id]['duration']}s")
    except Exception as e:
        logger.error(f"Conversion failed: {e}\n{traceback.format_exc()}")
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["duration"] = round(time.time() - tasks[task_id]["start_time"], 1)


@app.get("/status")
async def get_status(ids: str):
    task_ids = [t.strip() for t in ids.split(",") if t.strip()]
    results = {}
    for tid in task_ids:
        if tid in tasks:
            t = tasks[tid]
            results[tid] = {
                "filename": t["filename"],
                "file_size": t.get("file_size", 0),
                "status": t["status"],
                "progress": t.get("progress", 0),
                "total": t.get("total", 0),
                "error": t["error"],
                "duration": t.get("duration"),
            }
    return results


@app.get("/preview/{task_id}")
async def preview_file(task_id: str):
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        raise HTTPException(status_code=404, detail="File not ready")
    md_path = task["result_path"]
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    return PlainTextResponse(content)


@app.get("/download/{task_id}")
async def download_file(task_id: str):
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        raise HTTPException(status_code=404, detail="File not ready")
    md_path = task["result_path"]
    md_filename = Path(md_path).name
    return FileResponse(md_path, filename=md_filename, media_type="text/markdown")


@app.get("/download-all")
async def download_all(ids: str):
    task_ids = [t.strip() for t in ids.split(",") if t.strip()]
    done_tasks = [
        tasks[tid] for tid in task_ids
        if tid in tasks and tasks[tid]["status"] == "done"
    ]
    if not done_tasks:
        raise HTTPException(status_code=404, detail="No files ready")

    zip_path = UPLOAD_DIR / f"book2md_{uuid.uuid4().hex[:6]}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for t in done_tasks:
            md_path = t["result_path"]
            zf.write(md_path, Path(md_path).name)

    return FileResponse(
        str(zip_path),
        filename="book2md_output.zip",
        media_type="application/zip",
    )


@app.get("/history")
async def get_history():
    """Return all completed conversions."""
    result = []
    for tid, t in tasks.items():
        if t["status"] == "done":
            result.append({
                "task_id": tid,
                "filename": t["filename"],
                "file_size": t.get("file_size", 0),
                "duration": t.get("duration"),
            })
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
