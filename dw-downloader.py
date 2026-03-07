import os
import sys
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import questionary
from questionary import Style
import yt_dlp
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.align import Align
import time

# Console setup
console = Console()

# Path setup
HOME_DIR = str(Path.home())
DOWNLOADS_DIR = os.path.join(HOME_DIR, "Downloads")
EXTENSION_DIR = os.path.join(HOME_DIR, "dw_extension")

# Custom style for prompts
custom_style = Style([
    ('qmark', 'fg:#00ff00 bold'),           
    ('question', 'fg:#00ffff bold'),        
    ('answer', 'fg:#00ff00 bold'),          
    ('pointer', 'fg:#ff00ff bold'),         
    ('highlighted', 'fg:#00ff00 bold'),     
    ('selected', 'fg:#00ff00'),             
    ('separator', 'fg:#666666'),            
    ('instruction', 'fg:#888888'),          
])

# ==========================================
# ASCII Art Banner
# ==========================================
def show_banner():
    banner = """

                                                                   
   ██████╗  ██████╗ ██╗    ██╗███╗   ██╗██╗      ██████╗  █████╗  ██████╗
   ██╔══██╗██╔═══██╗██║    ██║████╗  ██║██║     ██╔═══██╗██╔══██╗ ██╔══██╗
   ██║  ██║██║   ██║██║ █╗ ██║██╔██╗ ██║██║     ██║   ██║███████║ ██║  ██║
   ██║  ██║██║   ██║██║███╗██║██║╚██╗██║██║     ██║   ██║██╔══██║ ██║  ██║
   ██████╔╝╚██████╔╝╚███╔███╔╝██║ ╚████║███████╗╚██████╔╝██║  ██║ ██████╔╝
   ╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ 
                                                                                    
                    ███╗   ██╗ ██████╗ ██╗    ██╗ ██╗                   
                    ████╗  ██║██╔═══██╗██║    ██║ ██║                   
                    ██║╚██╗██║██║   ██║██║███╗██║ ╚═╝                   
                    ██║ ╚████║╚██████╔╝╚███╔███╔╝ ██╗                   
                    ╚═╝  ╚═══╝ ╚═════╝  ╚══╝╚══╝  ╚═╝                   


    """
    
    console.clear()
    console.print(banner, style="bold cyan")
    time.sleep(0.5)

# ==========================================
# Local server (for communicating with the extension)
# ==========================================
class ExtensionHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "connected"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/download':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode())
            
            url = data.get('url')
            dl_type = data.get('dl_type')
            if dl_type == 'song':
                quality = None
                format_type = 'mp3'
            else:
                quality = data.get('quality', 'HD (720p)')
                format_type = data.get('format_type', 'mp4')
            
            if url:
                threading.Thread(target=download_video, args=(url, quality, format_type), daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-type")
        self.end_headers()

    def log_message(self, format, *args):
        pass

def start_local_server():
    server = HTTPServer(('localhost', 65432), ExtensionHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

# ==========================================
# Create Google Chrome extension
# ==========================================
def create_extension(silent=False):
    os.makedirs(EXTENSION_DIR, exist_ok=True)
    
    manifest = {
        "manifest_version": 3,
        "name": "DW YouTube Connector",
        "version": "1.0",
        "description": "Connects browser to DW terminal downloader.",
        "action": {"default_popup": "popup.html"},
        "permissions": ["activeTab", "scripting"],
        "content_scripts": [
            {
                "matches": ["<all_urls>"],
                "js": ["content.js"]
            }
        ]
    }
    with open(os.path.join(EXTENSION_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
        
    popup_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { width: 250px; font-family: sans-serif; text-align: center; padding: 10px; background: #1e1e2e; color: #cdd6f4;}
        #status { font-weight: bold; margin-bottom: 15px; }
        .connected { color: #a6e3a1; }
        .disconnected { color: #f38ba8; }
        button { background: #89b4fa; color: #1e1e2e; border: none; padding: 8px; margin: 5px; cursor: pointer; border-radius: 5px; font-weight: bold; width: 90%;}
        button:hover { background: #b4befe; }
        select { padding: 5px; margin: 5px; width: 90%; background: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px;}
        .section { margin-top: 15px; border-top: 1px solid #45475a; padding-top: 10px;}
    </style>
</head>
<body>
    <h3>DW Downloader</h3>
    <div id="status" class="disconnected">Disconnected</div>
    
    <button id="btnSong">Download Song (MP3)</button>
    
    <div class="section">
        <select id="videoQuality">
            <option value="FHD (1080p)">FHD (1080p)</option>
            <option value="HD (720p)">HD (720p)</option>
            <option value="SD (480p)">SD (480p)</option>
        </select>
        <select id="videoFormat">
            <option value="mp4">mp4</option>
            <option value="mkv">mkv</option>
        </select>
        <button id="btnVideo">Download Video</button>
    </div>
    <div id="msg" style="margin-top: 10px; font-size: 12px; color: #a6e3a1;"></div>
    <script src="popup.js"></script>
</body>
</html>"""
    with open(os.path.join(EXTENSION_DIR, "popup.html"), "w", encoding="utf-8") as f:
        f.write(popup_html)

    popup_js = """
    function checkConnection() {
        fetch('http://localhost:65432/status')
            .then(response => response.json())
            .then(data => {
                if(data.status === "connected") {
                    let statusEl = document.getElementById('status');
                    statusEl.innerText = "Connected";
                    statusEl.className = "connected";
                }
            })
            .catch(err => {
                let statusEl = document.getElementById('status');
                statusEl.innerText = "Disconnected";
                statusEl.className = "disconnected";
            });
    }
    checkConnection();
    setInterval(checkConnection, 3000);

    function sendDownloadRequest(data) {
        chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
            let url = tabs[0].url;
            data.url = url;
            document.getElementById('msg').innerText = 'Sending...';
            document.getElementById('msg').style.color = '#a6e3a1';
            fetch('http://localhost:65432/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            }).then(res => res.json()).then(resData => {
                document.getElementById('msg').innerText = 'Download started in terminal!';
                setTimeout(() => { document.getElementById('msg').innerText = ''; }, 3000);
            }).catch(err => {
                document.getElementById('msg').innerText = 'Error communicating with server';
                document.getElementById('msg').style.color = '#f38ba8';
            });
        });
    }

    document.getElementById('btnSong').addEventListener('click', () => {
        sendDownloadRequest({
            dl_type: 'song',
            format_type: 'mp3'
        });
    });

    document.getElementById('btnVideo').addEventListener('click', () => {
        sendDownloadRequest({
            dl_type: 'video',
            quality: document.getElementById('videoQuality').value,
            format_type: document.getElementById('videoFormat').value
        });
    });
    """
    with open(os.path.join(EXTENSION_DIR, "popup.js"), "w", encoding="utf-8") as f:
        f.write(popup_js)
        
    content_js = """
//  DW Floating Smart Download Button - Safe injection
if (!document.getElementById('dw-floating-btn')) {
    let btn = document.createElement('button');
    btn.id = 'dw-floating-btn';
    btn.innerText = ' DW';
    btn.title = 'Download Current Video';
    btn.style.cssText = 'position: fixed; bottom: 30px; right: 30px; z-index: 2147483647; background: #89b4fa; color: #1e1e2e; border: none; width: 60px; height: 60px; border-radius: 50%; cursor: pointer; font-weight: bold; font-family: sans-serif; box-shadow: 0 4px 10px rgba(0,0,0,0.5); font-size: 16px; display: flex; align-items: center; justify-content: center; opacity: 0.8; transition: all 0.3s;';
    
    btn.onmouseover = () => {
        btn.style.opacity = '1';
        btn.style.transform = 'scale(1.1)';
    };
    btn.onmouseout = () => {
        btn.style.opacity = '0.8';
        btn.style.transform = 'scale(1)';
    };

    btn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        
        // Smart URL detection for active video
        let url = window.location.href;
        if (url.includes('tiktok.com')) {
            let videos = document.querySelectorAll('video');
            for(let v of videos) {
                let rect = v.getBoundingClientRect();
                // Check if video is mostly in viewport
                if(rect.top >= -100 && rect.bottom <= window.innerHeight + 100) {
                   let container = v.closest('[data-e2e="recommend-list-item-container"]') || v.closest('.video-feed-item');
                   if (container) {
                       let link = container.querySelector('a[href*="/video/"]');
                       if (link) {
                           url = link.href;
                           break;
                       }
                   }
                }
            }
        }
        
        let originalText = btn.innerText;
        btn.innerText = '⏳';
        
        fetch('http://localhost:65432/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                url: url,
                dl_type: 'video',
                quality: 'HD (720p)',
                format_type: 'mp4'
            })
        }).then(() => {
            btn.innerText = '✅';
            setTimeout(() => btn.innerText = originalText, 2000);
        }).catch(() => {
            btn.innerText = '❌';
            setTimeout(() => btn.innerText = originalText, 2000);
        });
    };
    
    document.body.appendChild(btn);
}
"""
    with open(os.path.join(EXTENSION_DIR, "content.js"), "w", encoding="utf-8") as f:
        f.write(content_js)
        
    if not silent:
        console.print("\\n[bold green]Extension directory created successfully at:[/bold green]", EXTENSION_DIR)
        console.print("[yellow]To install: Open Chrome, go to chrome://extensions, enable 'Developer mode', click 'Load unpacked' and select the 'dw_extension' folder.[/yellow]\\n")

# ==========================================
# Progress Hook for yt-dlp
# ==========================================
class DownloadProgressHook:
    def __init__(self):
        self.progress = None
        self.task_id = None
        
    def __call__(self, d):
        if d['status'] == 'downloading':
            if self.progress is None:
                self.progress = Progress(
                    SpinnerColumn(spinner_name="dots"),
                    TextColumn("[bold blue]{task.description}"),
                    BarColumn(bar_width=40),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TimeRemainingColumn(),
                    console=console
                )
                self.progress.start()
                self.task_id = self.progress.add_task(
                    "[cyan]Downloading...", 
                    total=100
                )
            
            # Update progress
            if 'downloaded_bytes' in d and 'total_bytes' in d:
                percentage = (d['downloaded_bytes'] / d['total_bytes']) * 100
                self.progress.update(self.task_id, completed=percentage)
            elif '_percent_str' in d:
                try:
                    percent = float(d['_percent_str'].strip().replace('%', ''))
                    self.progress.update(self.task_id, completed=percent)
                except:
                    pass
                    
        elif d['status'] == 'finished':
            if self.progress:
                self.progress.update(self.task_id, completed=100)
                self.progress.stop()
                console.print("\\n[bold green]Download Complete! Processing...[/bold green]")

# ==========================================
# Download Engine
# ==========================================
def download_video(url, quality, format_type):
    progress_hook = DownloadProgressHook()
    
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
    }

    if format_type == 'mp3':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        if quality == 'FHD (1080p)':
            ydl_opts['format'] = f'bestvideo[height<=1080]+bestaudio/best'
        elif quality == 'HD (720p)':
            ydl_opts['format'] = f'bestvideo[height<=720]+bestaudio/best'
        else:
            ydl_opts['format'] = f'bestvideo[height<=480]+bestaudio/best'
            
        if format_type == 'mkv':
            ydl_opts['merge_output_format'] = 'mkv'
        else:
            ydl_opts['merge_output_format'] = 'mp4'

    console.print("\\n[bold yellow]Starting download... Please wait.[/bold yellow]\\n")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        success_panel = Panel(
            Align.center(
                f"[bold green]Download Completed Successfully![/bold green]\\n\\n"
                f"[cyan]Saved to:[/cyan] [yellow]{DOWNLOADS_DIR}[/yellow]",
                vertical="middle"
            ),
            box=box.DOUBLE_EDGE,
            style="bold green",
            border_style="bright_green"
        )
        console.print(success_panel)
        time.sleep(1)
        
    except Exception as e:
        console.print(f"\\n[bold red]Error during download:[/bold red] {e}\\n")

# ==========================================
# Main Function
# ==========================================
def main():
    show_banner()
    
    # Check if user wants to install extension
    ext_manifest = os.path.join(EXTENSION_DIR, "manifest.json")
    if not os.path.exists(ext_manifest):
        install_ext = questionary.confirm(
            "Install browser extension for smart downloads?",
            default=True,
            style=custom_style
        ).ask()
        
        if install_ext:
            create_extension(silent=False)
    else:
        # Silently update the extension to inject the new content.js
        create_extension(silent=True)

    start_local_server()
    console.print("[bold green]Local server started on port 65432[/bold green]\\n")

    while True:
        try:
            console.rule("[bold cyan]New Download[/bold cyan]", style="cyan")
            
            url = questionary.text(
                "Enter YouTube URL (or type 'exit' to quit):",
                style=custom_style
            ).ask()
            
            if not url:
                continue
            if url.lower() == 'exit':
                console.print("\\n[bold cyan]Thank you for using Download Now![/bold cyan]\\n")
                break

            dl_type = questionary.select(
                "Download Type:",
                choices=['Video', 'Song'],
                style=custom_style
            ).ask()

            if dl_type == 'Video':
                quality = questionary.select(
                    "Choose Quality:",
                    choices=['FHD (1080p)', 'HD (720p)', 'SD (480p)'],
                    style=custom_style
                ).ask()

                format_type = questionary.select(
                    "Choose Format:",
                    choices=['mp4', 'mkv'],
                    style=custom_style
                ).ask()
            else:
                quality = None
                format_type = 'mp3'

            if url and format_type:
                download_video(url, quality, format_type)
                
                another = questionary.confirm(
                    "Download another video?",
                    default=True,
                    style=custom_style
                ).ask()
                
                if not another:
                    console.print("\\n[bold cyan]Thank you for using Download Now![/bold cyan]\\n")
                    break
                    
        except KeyboardInterrupt:
            console.print("\\n\\n[bold yellow]Process interrupted by user.[/bold yellow]")
            sys.exit(0)
        except Exception as e:
            console.print(f"\\n[bold red]Error:[/bold red] {e}\\n")

if __name__ == "__main__":
    main()