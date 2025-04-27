import os
import subprocess
import pandas as pd
import sys
from pathlib import Path
import shlex
import re
from datetime import timedelta
import itertools
from send2trash import send2trash

FFPROBE_PATH = "F:\\Downloads\\Free_MP4_to_MP3_Converter_64bit_PORTABLE\\tools\\FFmpeg64\\ffprobe.exe"
FFMPEG_PATH = "F:\\Downloads\\Free_MP4_to_MP3_Converter_64bit_PORTABLE\\tools\\FFmpeg64\\ffmpeg.exe"

VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv']
# SPINNER = itertools.cycle(['|', '/', '-', '\\'])
SPINNER = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])

def check_encoder_support(encoder):
    """Sprawdza, czy dany enkoder jest obsługiwany przez FFmpeg."""
    try:
        result = subprocess.run([FFMPEG_PATH, "-encoders"], capture_output=True, text=True, check=True, shell=True)
        return encoder in result.stdout
    except subprocess.CalledProcessError:
        return False

def get_video_info(file_path):
    """Pobiera informacje o pliku wideo, w tym wszystkie ścieżki audio i napisy."""
    if not os.path.isfile(FFPROBE_PATH):
        print(f"❌  Błąd: ffprobe.exe nie znaleziono w: {FFPROBE_PATH}")
        return None
    if not os.path.isfile(file_path):
        print(f"❌  Błąd: Plik nie istnieje: {file_path}")
        return None

    try:
        video_info = subprocess.run([FFPROBE_PATH, "-v", "error", "-select_streams", "v:0", "-show_entries", 
                                     "stream=codec_name,width,height", "-of", "csv=p=0", file_path], 
                                    capture_output=True, text=True, check=True, shell=True).stdout.strip().split(',')
        audio_info = subprocess.run([FFPROBE_PATH, "-v", "error", "-select_streams", "a", "-show_entries", 
                                     "stream=codec_name", "-of", "csv=p=0", file_path], 
                                    capture_output=True, text=True, check=True, shell=True).stdout.strip().split('\n')
        audio_codecs = [codec.strip() for codec in audio_info if codec.strip()]
        subtitle_info = subprocess.run([FFPROBE_PATH, "-v", "error", "-select_streams", "s", "-show_entries", 
                                       "stream=codec_name", "-of", "csv=p=0", file_path], 
                                      capture_output=True, text=True, check=True, shell=True).stdout.strip().split('\n')
        subtitle_codecs = [codec.strip() for codec in subtitle_info if codec.strip()]
        size_info = os.path.getsize(file_path)
        duration_info = subprocess.run([FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration", 
                                        "-sexagesimal", "-of", "default=noprint_wrappers=1:nokey=1", file_path], 
                                       capture_output=True, text=True, check=True, shell=True).stdout.strip().split('.')[0]
    except subprocess.CalledProcessError as e:
        print(f"❌  Błąd analizy pliku {file_path}: {e}")
        return None

    return {
        "file_name": os.path.basename(file_path),
        "extension": os.path.splitext(file_path)[1],
        "size": f"{size_info / (1024 * 1024 * 1024):.2f} GB",
        "duration": duration_info,
        "video_codec": video_info[0] if video_info else None,
        "audio_codecs": audio_codecs if audio_codecs else [None],
        "subtitle_codecs": subtitle_codecs if subtitle_codecs else [],
        "resolution": f"{int(video_info[1])}x{int(video_info[2])}" if len(video_info) > 2 else None
    }

def get_duration_seconds(file_path):
    """Pobiera czas trwania pliku w sekundach."""
    try:
        duration = float(subprocess.run([FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration", 
                                        "-of", "default=noprint_wrappers=1:nokey=1", file_path], 
                                       capture_output=True, text=True, check=True, shell=True).stdout.strip())
        return duration
    except subprocess.CalledProcessError:
        return 0

def check_projector_support(info):
    """Sprawdza zgodność pliku z projektorem i zwraca listę powodów nieobsługiwania."""
    reasons = []
    video_needs_conversion = False
    audio_needs_conversion = [False] * len(info["audio_codecs"])

    for i, codec in enumerate(info["audio_codecs"]):
        if codec in ["ac3", "eac3"]:
            reasons.append(f"Nieobsługiwany kodek audio w ścieżce {i} ({codec})")
            audio_needs_conversion[i] = True

    if info["video_codec"] != "hevc":
        reasons.append("Nieobsługiwany kodek wideo (musi być HEVC)")
        video_needs_conversion = True
    if info["resolution"]:
        width, height = map(int, info["resolution"].split("x"))
        if width > 1920 or height > 1080:
            reasons.append("Rozdzielczość wyższa niż 1920x1080")
            video_needs_conversion = True

    return reasons, video_needs_conversion, audio_needs_conversion

def convert_file(file_path, current_file=1, total_files=1):
    """Konwertuje plik do formatu obsługiwanego przez projektor (HEVC i AAC), zachowując wszystkie ścieżki audio i napisy."""
    if not os.path.isfile(FFMPEG_PATH):
        print(f"❌  Błąd: ffmpeg.exe nie znaleziono w: {FFMPEG_PATH}")
        return False

    use_nvenc = check_encoder_support("hevc_nvenc")
    if not use_nvenc and not check_encoder_support("libx265"):
        print("❌  Błąd: FFmpeg nie obsługuje ani hevc_nvenc, ani libx265. Zaktualizuj FFmpeg.")
        return False
    if not check_encoder_support("aac"):
        print("❌  Błąd: FFmpeg nie obsługuje enkodera aac.")
        return False

    output_file = os.path.splitext(file_path)[0] + "_converted.mp4"
    total_duration = get_duration_seconds(file_path)
    if total_duration == 0:
        print("❌  Błąd: Nie udało się pobrać czasu trwania pliku.")
        return False

    info = get_video_info(file_path)
    if not info:
        return False

    _, video_needs_conversion, audio_needs_conversion = check_projector_support(info)

    if video_needs_conversion:
        if use_nvenc:
            video_encoder = "hevc_nvenc"
            video_params = ["-preset", "p5", "-rc", "vbr", "-cq", "24"]
        else:
            video_encoder = "libx265"
            video_params = ["-preset", "ultrafast"]
        if info["resolution"]:
            width, height = map(int, info["resolution"].split("x"))
            if width > 1920 or height > 1080:
                video_params.extend(["-vf", "scale=1920:-2"])
    else:
        video_encoder = "copy"
        video_params = []

    audio_params = []
    for i, needs_conversion in enumerate(audio_needs_conversion):
        audio_params.extend([f"-c:a:{i}", "aac" if needs_conversion else "copy"])

    subtitle_params = ["-c:s", "mov_text"] if info["subtitle_codecs"] else []

    cmd = [FFMPEG_PATH, "-i", file_path, "-map", "0:v", "-map", "0:a"]
    if info["subtitle_codecs"]:
        cmd.extend(["-map", "0:s"])  # Mapuj napisy, jeśli istnieją
    cmd.extend(["-c:v", video_encoder, "-hide_banner", "-loglevel", "warning", "-stats", "-y"] + 
               video_params + audio_params + subtitle_params + [output_file])
    
    try:
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        last_progress = -1

        for line in process.stdout:
            match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})", line)
            if match:
                current_time_str = match.group(1)
                h, m, s = map(float, current_time_str.split(':'))
                current_time = h * 3600 + m * 60 + s
                progress = min(int((current_time / total_duration) * 100), 100)
                
                speed_match = re.search(r"speed=([\d.]+)x", line)
                speed = float(speed_match.group(1)) if speed_match else 1.0
                remaining_time = (total_duration - current_time) / speed if speed > 0 else 0
                remaining_time_str = f"{int(remaining_time // 60)} min" if remaining_time > 60 else f"{int(remaining_time)} s"
                
                if progress >= last_progress:
                    current_time_str = str(timedelta(seconds=int(current_time))).split('.')[0]
                    spinner_char = next(SPINNER)
                    print(f"\r {spinner_char} {current_file}/{total_files} Konwertowanie pliku: {os.path.basename(file_path)} | Postęp: {progress:3d}% | Pozostało: {remaining_time_str:<10}", end="")
                    sys.stdout.flush()
                    last_progress = progress

        process.wait()
        if process.returncode == 0:
            print(f"\r✅ {current_file}/{total_files} Plik został przekonwertowany: {output_file}" + " " * 50, end="")
            output_size = os.path.getsize(output_file) / (1024 * 1024 * 1024)
            input_size = os.path.getsize(file_path) / (1024 * 1024 * 1024)
            if output_size > input_size:
                print(f"\n⚠️  Ostrzeżenie: Rozmiar pliku wyjściowego ({output_size:.2f} GB) jest większy niż oryginalny ({input_size:.2f} GB).")
            
            if os.path.isfile(file_path):
                try:
                    send2trash(file_path)
                except Exception as e:
                    print(f"\n⚠️  Nie udało się przenieść pliku do kosza: {str(e)}")
            return True
        else:
            print(f"\n❌  Błąd konwersji: Sprawdź FFmpeg lub plik wejściowy.")
            if os.path.exists(output_file):
                os.remove(output_file)
            return False

    except KeyboardInterrupt:
        print(f"\n\n⚠️  Przerwano konwersję pliku: {os.path.basename(file_path)}")
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
        if os.path.exists(output_file):
            os.remove(output_file)
            print(f"🗑️  Usunięto niedokończony plik: {output_file}")
        raise

    except Exception as e:
        print(f"\n❌  Błąd konwersji: {str(e)}")
        if os.path.exists(output_file):
            os.remove(output_file)
        return False

def process_file(file_path):
    """Przetwarza plik i zwraca informacje oraz status zgodności."""
    info = get_video_info(file_path)
    if not info:
        return None, None

    print(f"\n\n📄  Analiza pliku: {info['file_name']}")
    info_display = info.copy()
    info_display.pop("audio_codecs")
    info_display.pop("subtitle_codecs")
    print(pd.DataFrame([info_display]).to_string(index=False, justify='left'))
    print("Ścieżki audio:")
    for i, codec in enumerate(info["audio_codecs"]):
        print(f"  - Ścieżka {i}: {codec if codec else 'nieznany'}")
    if info["subtitle_codecs"]:
        print("Ścieżki napisów:")
        for i, codec in enumerate(info["subtitle_codecs"]):
            print(f"  - Ścieżka {i}: {codec if codec else 'nieznany'}")

    reasons, _, _ = check_projector_support(info)
    if reasons:
        print("⚠️  Plik nieobsługiwany przez projektor:")
        for reason in reasons:
            print(f"  - {reason}")
    else:
        print("✅  Plik obsługiwany przez projektor")
    
    return info, reasons

def get_files_to_process(paths):
    """Zwraca listę plików do przetworzenia na podstawie podanych ścieżek, przeszukując rekurencyjnie podfoldery."""
    files = []
    for path in paths:
        if os.path.isfile(path) and os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS:
            files.append(path)
        elif os.path.isdir(path):
            for root, _, files_in_dir in os.walk(path):
                for file in files_in_dir:
                    if os.path.splitext(file)[1].lower() in VIDEO_EXTENSIONS:
                        files.append(os.path.join(root, file))
    return files

if __name__ == "__main__":
    while True:
        try:
            if len(sys.argv) > 1:
                files_to_process = get_files_to_process(sys.argv[1:])
            else:
                while True:
                    user_input = input("📂  Podaj ścieżki do plików lub folderów (użyj cudzysłowów dla nazw ze spacjami): ")

                    file_paths = [str(Path(p)) for p in user_input.split()]
                    file_paths2 = shlex.split(user_input)

                    valid_paths = set()
                    for path in file_paths + file_paths2:
                        if Path(path).exists():
                            valid_paths.add(path)

                    if not valid_paths:
                        print("❌  Podana ścieżka nie istnieje.\n")
                        continue
                    
                    files_to_process = get_files_to_process(list(valid_paths))
                    break

            unsupported_files = []
            
            for file in files_to_process:
                info, reasons = process_file(file)
                if reasons:
                    unsupported_files.append(file)
            
            if unsupported_files:
                print(f"\n📋  Znaleziono {len(unsupported_files)} nieobsługiwanych plików:")
                for file in unsupported_files:
                    print(f"  - {os.path.basename(file)}")
                while True:
                    response = input("\nCzy chcesz przekonwertować wszystkie nieobsługiwane pliki do formatu obsługiwanego? (T/N): ")
                    if response.upper() == "T":
                        total_files = len(unsupported_files)
                        for i, file in enumerate(unsupported_files, 1):
                            print()
                            convert_file(file, current_file=i, total_files=total_files)
                        break
                    elif response.upper() == "N":
                        print()
                        break
                    else:
                        print("❌  Niepoprawna odpowiedź. Wybierz T lub N.")

        except KeyboardInterrupt:
            print("\n⚠️  Program przerwany przez użytkownika.")
            input("\nNaciśnij Enter, aby zamknąć program...")
            break