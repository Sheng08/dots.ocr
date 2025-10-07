from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
import os
from pathlib import Path
import tempfile
import uuid
import json
from dots_ocr.parser import DotsOCRParser
from dots_ocr.utils.consts import MIN_PIXELS, MAX_PIXELS

app = FastAPI(
    title="dotsOCR API",
    description="API for PDF and image text recognition using dotsOCR by Grant",
    version="1.0.0"
)

dots_parser = DotsOCRParser(
    ip="localhost",
    port=8000,
    dpi=200,
    min_pixels=MIN_PIXELS,
    max_pixels=MAX_PIXELS
)


class ParseRequest(BaseModel):
    prompt_mode: str = "prompt_layout_all_en"
    fitz_preprocess: bool = False


@app.post("/parse/image")
async def parse_image(
    file: UploadFile = File(...),
    prompt_mode: str = "prompt_layout_all_en",
    fitz_preprocess: bool = False
):
    try:
        if not file:
            raise HTTPException(status_code=400, detail="No file uploaded")
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="Missing filename")
        
        try:
            file_ext = Path(file.filename).suffix.lower()
        except TypeError:
            raise HTTPException(status_code=400, detail="Invalid filename format")
        
        if file_ext not in ['.jpg', '.jpeg', '.png']:
            raise HTTPException(status_code=400, detail="Invalid image format. Supported: .jpg, .jpeg, .png")
        
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        await file.seek(0)
        
        print(f"DEBUG: Creating temp file for {file.filename}")
        temp_dir = tempfile.mkdtemp()
        print(f"DEBUG: Created temp dir {temp_dir}")
        temp_path = os.path.join(temp_dir, f"upload_{uuid.uuid4().hex}{file_ext}")
        print(f"DEBUG: Temp file path will be {temp_path}")
        
        file_content = await file.read()
        print(f"DEBUG: Read {len(file_content)} bytes from upload")
        
        if not isinstance(temp_path, (str, bytes, os.PathLike)):
            raise HTTPException(
                status_code=500,
                detail=f"Invalid temp path type: {type(temp_path)}"
            )
        
        with open(temp_path, "wb") as buffer:
            buffer.write(file_content)
        print(f"DEBUG: Saved {len(file_content)} bytes to {temp_path}")
        
        if not os.path.exists(temp_path):
            raise HTTPException(
                status_code=500,
                detail="Failed to create temp file"
            )
        
        print(f"DEBUG: Temp file exists at {temp_path}")
        print(f"DEBUG: Calling parser with: {temp_path}")
        
        abs_temp_path = os.path.abspath(temp_path)
        if not os.path.exists(abs_temp_path):
            raise HTTPException(
                status_code=500,
                detail=f"Temp file not found at {abs_temp_path}"
            )
        
        output_dir = tempfile.mkdtemp()
        for f in os.listdir(output_dir):
            os.remove(os.path.join(output_dir, f))
        
        try:
            results = dots_parser.parse_image(
                input_path=abs_temp_path,
                filename="api_image",
                prompt_mode=prompt_mode,
                save_dir=output_dir,
                fitz_preprocess=fitz_preprocess
            )
            print(f"DEBUG: Parser completed successfully=={results}")
            
            result = results[0]
            layout_info_path = result.get('layout_info_path')
            full_layout_info = {}
            
            if layout_info_path and os.path.exists(layout_info_path):
                try:
                    with open(layout_info_path, 'r', encoding='utf-8') as f:
                        full_layout_info = json.load(f)
                except Exception as e:
                    print(f"WARNING: Failed to read layout info file: {str(e)}")
        
        except Exception as e:
            print(f"DEBUG: Parser error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Parser error: {str(e)}"
            )
        finally:
            if os.path.exists(abs_temp_path):
                os.remove(abs_temp_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
            if os.path.exists(output_dir):
                for f in os.listdir(output_dir):
                    os.remove(os.path.join(output_dir, f))
                os.rmdir(output_dir)
        
        return {
            "success": True,
            "total_pages": len(results),
            "results": [{
                "page_no": 0,
                "full_layout_info": full_layout_info
            }]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/parse/pdf")
async def parse_pdf(
    file: UploadFile = File(...),
    prompt_mode: str = "prompt_layout_all_en",
    fitz_preprocess: bool = False
):
    try:
        if not file:
            raise HTTPException(status_code=400, detail="No file uploaded")
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="Missing filename")
        
        try:
            if Path(file.filename).suffix.lower() != '.pdf':
                raise HTTPException(status_code=400, detail="Invalid PDF format. Only .pdf files accepted")
        except TypeError:
            raise HTTPException(status_code=400, detail="Invalid filename format")
        
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        await file.seek(0)
        
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, f"upload_{uuid.uuid4().hex}.pdf")
        
        with open(temp_path, "wb") as buffer:
            buffer.write(await file.read())
        
        output_dir = tempfile.mkdtemp()
        for f in os.listdir(output_dir):
            os.remove(os.path.join(output_dir, f))
        
        try:
            results = dots_parser.parse_pdf(
                input_path=temp_path,
                filename="api_pdf",
                prompt_mode=prompt_mode,
                save_dir=output_dir
            )
            print(f"DEBUG: Parser completed successfully=={results}")
            
            formatted_results = []
            for result in results:
                layout_info_path = result.get('layout_info_path')
                full_layout_info = {}
                
                if layout_info_path and os.path.exists(layout_info_path):
                    try:
                        with open(layout_info_path, 'r', encoding='utf-8') as f:
                            full_layout_info = json.load(f)
                    except Exception as e:
                        print(f"WARNING: Failed to read layout info file: {str(e)}")
                
                formatted_results.append({
                    "page_no": result.get('page_no'),
                    "full_layout_info": full_layout_info
                })
            
            return {
                "success": True,
                "total_pages": len(results),
                "results": formatted_results
            }
        
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
            if os.path.exists(output_dir):
                for f in os.listdir(output_dir):
                    os.remove(os.path.join(output_dir, f))
                os.rmdir(output_dir)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/parse/file")
async def parse_file(
    file: UploadFile = File(...),
    prompt_mode: str = "prompt_layout_all_en",
    fitz_preprocess: bool = False
):
    try:
        if not file:
            raise HTTPException(status_code=400, detail="No file uploaded")
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="Missing filename")
        
        try:
            file_ext = Path(file.filename).suffix.lower()
        except TypeError:
            raise HTTPException(status_code=400, detail="Invalid filename format")
        
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        await file.seek(0)
        
        if file_ext == '.pdf':
            return await parse_pdf(file, prompt_mode, fitz_preprocess)
        elif file_ext in ['.jpg', '.jpeg', '.png']:
            return await parse_image(file, prompt_mode, fitz_preprocess)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
