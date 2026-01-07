```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import yt_dlp
import io

app = FastAPI(title="M7X YouTube Downloader API")

# CORS - السماح لجميع الدومينات
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp4"  # mp4, webm, mkv, avi, mp3, aac, flac, wav, ogg
    quality: Optional[str] = "720"  # 360, 480, 720, 1080, 1440, 2160
    start_time: Optional[str] = None  # "00:01:30"
    end_time: Optional[str] = None    # "00:05:00"

class VideoInfo(BaseModel):
    url: str

def get_format_opts(format: str, quality: str) -> dict:
    """تحديد خيارات التنسيق والجودة"""
    
    audio_formats = ['mp3', 'aac', 'flac', 'wav', 'ogg']
    
    if format in audio_formats:
        return {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format,
                'preferredquality': '320',
            }],
        }
    
    # Video formats
    quality_map = {
        '360': 'bestvideo[height<=360]+bestaudio/best[height<=360]',
        '480': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
        '720': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        '1080': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        '1440': 'bestvideo[height<=1440]+bestaudio/best[height<=1440]',
        '2160': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]',
    }
    
    format_string = quality_map.get(quality, quality_map['720'])
    
    opts = {
        'format': format_string,
    }
    
    if format != 'mp4':
        opts['postprocessors'] = [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': format,
        }]
    
    return opts

@app.get("/")
async def root():
    return {"status": "ok", "message": "M7X YouTube Downloader API"}

@app.post("/info")
async def get_video_info(request: VideoInfo):
    """الحصول على معلومات الفيديو"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=False)
            
            return {
                "success": True,
                "data": {
                    "title": info.get('title'),
                    "thumbnail": info.get('thumbnail'),
                    "duration": info.get('duration'),
                    "channel": info.get('uploader'),
                    "view_count": info.get('view_count'),
                    "description": info.get('description', '')[:500],
                    "formats": [
                        {"quality": "360p", "ext": "mp4"},
                        {"quality": "480p", "ext": "mp4"},
                        {"quality": "720p", "ext": "mp4"},
                        {"quality": "1080p", "ext": "mp4"},
                    ]
                }
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/download")
async def download_video(request: DownloadRequest):
    """تحميل الفيديو وإرساله مباشرة (Streaming)"""
    try:
        # Buffer لتخزين البيانات مؤقتاً في الذاكرة
        buffer = io.BytesIO()
        
        format_opts = get_format_opts(request.format, request.quality or "720")
        
        ydl_opts = {
            **format_opts,
            'quiet': True,
            'no_warnings': True,
            'outtmpl': '-',  # Output to stdout
        }
        
        # إضافة خيارات القص إذا تم تحديدها
        postprocessor_args = []
        if request.start_time or request.end_time:
            if request.start_time:
                postprocessor_args.extend(['-ss', request.start_time])
            if request.end_time:
                postprocessor_args.extend(['-to', request.end_time])
            
            ydl_opts['postprocessor_args'] = {
                'ffmpeg': postprocessor_args
            }
        
        # الحصول على معلومات الفيديو أولاً
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(request.url, download=False)
            title = info.get('title', 'video')
            # تنظيف اسم الملف
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        # تحميل الفيديو إلى الذاكرة
        ydl_opts['outtmpl'] = '-'
        
        def generate():
            """Generator لإرسال البيانات تدريجياً"""
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # استخدام download_to_buffer أو طريقة بديلة
                try:
                    # تحميل إلى ملف مؤقت في الذاكرة
                    import tempfile
                    import os
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{request.format}') as tmp:
                        tmp_path = tmp.name
                    
                    ydl_opts['outtmpl'] = tmp_path
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([request.url])
                    
                    # قراءة الملف وإرساله
                    with open(tmp_path, 'rb') as f:
                        while chunk := f.read(1024 * 1024):  # 1MB chunks
                            yield chunk
                    
                    # حذف الملف المؤقت
                    os.unlink(tmp_path)
                    
                except Exception as e:
                    raise e
        
        # تحديد نوع المحتوى
        content_types = {
            'mp4': 'video/mp4',
            'webm': 'video/webm',
            'mkv': 'video/x-matroska',
            'avi': 'video/x-msvideo',
            'mp3': 'audio/mpeg',
            'aac': 'audio/aac',
            'flac': 'audio/flac',
            'wav': 'audio/wav',
            'ogg': 'audio/ogg',
        }
        
        content_type = content_types.get(request.format, 'application/octet-stream')
        filename = f"{safe_title}.{request.format}"
        
        return StreamingResponse(
            generate(),
            media_type=content_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Access-Control-Expose-Headers': 'Content-Disposition'
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/batch-info")
async def get_batch_info(urls: list[str]):
    """الحصول على معلومات عدة فيديوهات"""
    results = []
    
    for url in urls:
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                results.append({
                    "url": url,
                    "success": True,
                    "data": {
                        "title": info.get('title'),
                        "thumbnail": info.get('thumbnail'),
                        "duration": info.get('duration'),
                    }
                })
        except Exception as e:
            results.append({
                "url": url,
                "success": False,
                "error": str(e)
            })
    
    return {"results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```
