import os
import subprocess
import time
import pandas as pd
import sys
import shlex
import re
from datetime import timedelta
import itertools

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
    """Pobiera informacje o pliku wideo."""
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
        print(f"❌  Błąd analizy pliku {file_path}: {e}")
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
    audio_needs_conversion = False

    # Sprawdzenie kodeka audio
    if info["audio_codec"] in ["ac3", "eac3"]:
        reasons.append("Nieobsługiwany kodek audio (ac3/eac3)")
        audio_needs_conversion = True

    # Sprawdzenie kodeka wideo i rozdzielczości
    if info["video_codec"] != "hevc":
        reasons.append("Nieobsługiwany kodek wideo (musi być HEVC)")
        video_needs_conversion = True
    if info["resolution"]:
        width, height = map(int, info["resolution"].split("x"))
        if width > 1920 or height > 1080:
            reasons.append("Rozdzielczość wyższa niż 1920x1080")
            video_needs_conversion = True

    return reasons, video_needs_conversion, audio_needs_conversion

def convert_file(file_path):
    """Konwertuje plik do formatu obsługiwanego przez projektor (HEVC i AAC)."""
    if not os.path.isfile(FFMPEG_PATH):
        print(f"❌  Błąd: ffmpeg.exe nie znaleziono w: {FFMPEG_PATH}")
        return False

    # Sprawdzenie dostępności enkoderów
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

    # Pobranie informacji o pliku
    info = get_video_info(file_path)
    if not info:
        return False

    # Określenie, które strumienie wymagają konwersji
    reasons, video_needs_conversion, audio_needs_conversion = check_projector_support(info)

    # Ustawienie parametrów wideo
    if video_needs_conversion:
        if use_nvenc:
            video_encoder = "hevc_nvenc"
            video_params = ["-preset", "p7", "-rc", "vbr", "-b:v", "5M"]
        else:
            video_encoder = "libx265"
            video_params = ["-preset", "ultrafast"]
        # Skalowanie, jeśli rozdzielczość przekracza 1920x1080
        if info["resolution"]:
            width, height = map(int, info["resolution"].split("x"))
            if width > 1920 or height > 1080:
                video_params.extend(["-vf", "scale=1920:-2"])
    else:
        video_encoder = "copy"
        video_params = []

    # Ustawienie parametrów audio
    audio_encoder = "aac" if audio_needs_conversion else "copy"
    audio_params = []

    # Budowanie polecenia FFmpeg
    cmd = [FFMPEG_PATH, "-i", file_path, "-c:v", video_encoder, "-c:a", audio_encoder, "-hide_banner", "-loglevel", "warning", "-stats", "-y"] + video_params + audio_params + [output_file]
    
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
                    print(f"\r{spinner_char} Konwertowanie pliku: {os.path.basename(file_path)} | Postęp: {progress:3d}% | Pozostało: {remaining_time_str:<10}", end="")
                    sys.stdout.flush()
                    last_progress = progress
        
        process.wait()
        if process.returncode == 0:
            print(f"\r✅  Plik został przekonwertowany: {output_file}" + " " * 50, end="")
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
            process.wait(timeout=1)  # Czekaj na zakończenie procesu
        except subprocess.TimeoutExpired:
            process.kill()  # Wymuś zabicie, jeśli nie zakończy się w czasie
        if os.path.exists(output_file):
            os.remove(output_file)
            print(f"🗑️  Usunięto niedokończony plik: {output_file}")
        raise  # Przekaż wyjątek do nadrzędnego bloku

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
    print(pd.DataFrame([info]).to_string(index=False, justify='left'))

    reasons, _, _ = check_projector_support(info)
    if reasons:
        print("⚠️  Plik nieobsługiwany przez projektor:")
        for reason in reasons:
            print(f"  - {reason}")
    else:
        print("✅  Plik obsługiwany przez projektor")
    
    return info, reasons

def get_files_to_process(paths):
    """Zwraca listę plików do przetworzenia na podstawie podanych ścieżek."""
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
    while True:
        try:
            if len(sys.argv) > 1:
                files_to_process = get_files_to_process(sys.argv[1:])
            else:
                while True:
                    user_input = input("📂  Podaj ścieżki do plików lub folderów (użyj cudzysłowów dla nazw ze spacjami): ")
                    file_paths = shlex.split(user_input)
                    if not file_paths:
                        print("❌  Nie podano ścieżek.\n")
                        continue
                    files_to_process = get_files_to_process(file_paths)
                    break

            # Lista nieobsługiwanych plików
            unsupported_files = []
            
            # Przetwarzanie wszystkich plików
            for file in files_to_process:
                info, reasons = process_file(file)
                if reasons:
                    unsupported_files.append(file)
            
            # Pytanie o konwersję wszystkich nieobsługiwanych plików
            if unsupported_files:
                print(f"\n📋  Znaleziono {len(unsupported_files)} nieobsługiwanych plików:")
                for file in unsupported_files:
                    print(f"  - {os.path.basename(file)}")
                while True:
                    response = input("\nCzy chcesz przekonwertować wszystkie nieobsługiwane pliki do formatu obsługiwanego? (T/N): ")
                    if response.upper() == "T":
                        for file in unsupported_files:
                            print()
                            convert_file(file)
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
input()