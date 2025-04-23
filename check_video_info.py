import os
import subprocess
import pandas as pd
import sys
import shlex

FFPROBE_PATH = "F:\\Downloads\\Free_MP4_to_MP3_Converter_64bit_PORTABLE\\tools\\FFmpeg64\\ffprobe.exe"

VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv']

def get_video_info(file_path):
    """Pobiera informacje o pliku wideo."""
    if not os.path.isfile(FFPROBE_PATH):
        print(f"❌ Błąd: ffprobe.exe nie znaleziono w: {FFPROBE_PATH}")
        return None
    if not os.path.isfile(file_path):
        print(f"❌ Błąd: Plik nie istnieje: {file_path}")
        return None

    try:
        video_info = subprocess.run([FFPROBE_PATH, "-v", "error", "-select_streams", "v:0", "-show_entries", 
                                     "stream=codec_name,width,height", "-of", "csv=p=0", file_path], 
                                    capture_output=True, text=True, check=True, shell=True).stdout.strip().split(',')
        audio_info = subprocess.run([FFPROBE_PATH, "-v", "error", "-select_streams", "a:0", "-show_entries", 
                                     "stream=codec_name", "-of", "csv=p=0", file_path], 
                                    capture_output=True, text=True, check=True, shell=True).stdout.strip()
        size_info = float(subprocess.run([FFPROBE_PATH, "-v", "error", "-show_entries", "format=size", 
                                          "-of", "default=noprint_wrappers=1:nokey=1", file_path], 
                                         capture_output=True, text=True, check=True, shell=True).stdout.strip())
        duration_info = subprocess.run([FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration", 
                                        "-sexagesimal", "-of", "default=noprint_wrappers=1:nokey=1", file_path], 
                                       capture_output=True, text=True, check=True, shell=True).stdout.strip().split('.')[0]
    except subprocess.CalledProcessError as e:
        print(f"❌ Błąd analizy pliku {file_path}: {e}")
        return None

    return {
        "file_name": os.path.basename(file_path),
        "extension": os.path.splitext(file_path)[1],
        "size": f"{size_info / (1024 * 1024 * 1024):.2f} GB",
        "duration": duration_info,
        "video_codec": video_info[0] if video_info else None,
        "audio_codec": audio_info if audio_info else None,
        "resolution": f"{int(video_info[1])}x{int(video_info[2])}" if len(video_info) > 2 else None
    }

def check_projector_support(info):
    """Sprawdza zgodność pliku z projektorem i zwraca listę powodów nieobsługiwania."""
    reasons = []
    if info["audio_codec"] in ["ac3", "eac3"]:
        reasons.append("Nieobsługiwany kodek audio (ac3/eac3)")
    if info["resolution"]:
        width, height = map(int, info["resolution"].split("x"))
        if width > 1920 or height > 1080:
            reasons.append("Rozdzielczość wyższa niż 1920x1080")
    return reasons

def process_file(file_path):
    """Przetwarza plik i wyświetla wyniki."""
    info = get_video_info(file_path)
    if not info:
        return

    print("\n🎬 Szczegóły pliku:")
    print(pd.DataFrame([info]).to_string(index=False))
    print()

    reasons = check_projector_support(info)
    if reasons:
        print("⚠️ Plik nieobsługiwany przez projektor! Powody:")
        for reason in reasons:
            print(f" - {reason}")
    else:
        print("✔️ Plik obsługiwany przez projektor")
    print()

def get_files_to_process(paths):
    """Zwraca listę plików do przetworzenia na podstawie podanych ścieżek (pliki lub foldery)."""
    files = []
    for path in paths:
        if os.path.isfile(path) and os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS:
            files.append(path)
        elif os.path.isdir(path):
            for file in os.listdir(path):
                file_path = os.path.join(path, file)
                if os.path.isfile(file_path) and os.path.splitext(file)[1].lower() in VIDEO_EXTENSIONS:
                    files.append(file_path)
    return files

if __name__ == "__main__":
    if len(sys.argv) > 1:
        files_to_process = get_files_to_process(sys.argv[1:])
        for file in files_to_process:
            process_file(file)
    else:
        while True:
            user_input = input("📂 Podaj ścieżki do plików lub folderów (użyj cudzysłowów dla nazw ze spacjami): ")
            file_paths = shlex.split(user_input)
            if not file_paths:
                print("❌ Nie podano ścieżek.")
                continue
            files_to_process = get_files_to_process(file_paths)
            for file in files_to_process:
                process_file(file)