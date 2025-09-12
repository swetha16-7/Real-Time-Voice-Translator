import os
import re
import sys
import time
import textwrap
import tempfile
import threading
import traceback
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

import speech_recognition as sr
from googletrans import Translator
from gtts import gTTS

# optional backends
try:
    import pygame
    PYGAME_AVAILABLE = True
except Exception:
    pygame = None
    PYGAME_AVAILABLE = False

try:
    from playsound import playsound
    PLAYSOUND_AVAILABLE = True
except Exception:
    playsound = None
    PLAYSOUND_AVAILABLE = False

# pydub playback (optional)
PYDUB_AVAILABLE = False
FFMPEG_EXISTS = shutil.which("ffmpeg") is not None or shutil.which("ffmpeg.exe") is not None
if FFMPEG_EXISTS:
    try:
        from pydub import AudioSegment
        from pydub.playback import play as pydub_play
        PYDUB_AVAILABLE = True
    except Exception:
        PYDUB_AVAILABLE = False

# init pygame mixer if available
if PYGAME_AVAILABLE:
    try:
        pygame.mixer.init()
    except Exception:
        PYGAME_AVAILABLE = False

# Globals
playback_lock = threading.Lock()
is_playing = False
is_paused = False
current_tts_files = []

# Config
MAX_TRANSLATE_CHARS = 4500
MAX_TTS_CHARS = 900
TTS_RETRIES = 3
TTS_BACKOFF = 1.0

# Languages
dic = {
    'afrikaans': 'af', 'albanian': 'sq', 'amharic': 'am', 'arabic': 'ar',
    'armenian': 'hy', 'azerbaijani': 'az', 'basque': 'eu', 'belarusian': 'be',
    'bengali': 'bn', 'bosnian': 'bs', 'bulgarian': 'bg', 'catalan': 'ca',
    'cebuano': 'ceb', 'chichewa': 'ny', 'chinese (simplified)': 'zh-cn',
    'chinese (traditional)': 'zh-tw', 'corsican': 'co', 'croatian': 'hr',
    'czech': 'cs', 'danish': 'da', 'dutch': 'nl', 'english': 'en',
    'esperanto': 'eo', 'estonian': 'et', 'filipino': 'tl', 'finnish': 'fi',
    'french': 'fr', 'frisian': 'fy', 'galician': 'gl', 'georgian': 'ka',
    'german': 'de', 'greek': 'el', 'gujarati': 'gu', 'haitian creole': 'ht',
    'hausa': 'ha', 'hebrew': 'he', 'hindi': 'hi', 'hmong': 'hmn',
    'hungarian': 'hu', 'icelandic': 'is', 'igbo': 'ig', 'indonesian': 'id',
    'irish': 'ga', 'italian': 'it', 'japanese': 'ja', 'javanese': 'jw',
    'kannada': 'kn', 'korean': 'ko', 'latin': 'la', 'latvian': 'lv',
    'lithuanian': 'lt', 'malay': 'ms', 'malayalam': 'ml', 'marathi': 'mr',
    'nepali': 'ne', 'norwegian': 'no', 'persian': 'fa', 'polish': 'pl',
    'portuguese': 'pt', 'punjabi': 'pa', 'romanian': 'ro', 'russian': 'ru',
    'spanish': 'es', 'swahili': 'sw', 'swedish': 'sv', 'tamil': 'ta',
    'telugu': 'te', 'thai': 'th', 'turkish': 'tr', 'ukrainian': 'uk',
    'urdu': 'ur', 'vietnamese': 'vi', 'zulu': 'zu', 'assamese': 'as'
}

translator = Translator()

# Utilities
def chunk_text_for_api(text, max_chars):
    text = text.strip()
    if not text:
        return []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 <= max_chars:
            current = (current + " " + s).strip() if current else s
        else:
            if current:
                chunks.append(current)
            if len(s) <= max_chars:
                current = s
            else:
                parts = textwrap.wrap(s, max_chars, break_long_words=False, break_on_hyphens=False)
                for p in parts[:-1]:
                    chunks.append(p)
                current = parts[-1]
    if current:
        chunks.append(current)
    return chunks

def generate_tts_files(text, lang_code, retries=TTS_RETRIES, backoff=TTS_BACKOFF):
    tmp_files = []
    if not text or not text.strip():
        return tmp_files
    chunks = chunk_text_for_api(text, MAX_TTS_CHARS)
    for idx, chunk in enumerate(chunks, 1):
        success = False
        last_exc = None
        for attempt in range(1, retries + 1):
            tmp_path = None
            try:
                tf = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp_path = tf.name
                tf.close()
                gTTS(text=chunk, lang=lang_code, slow=False).save(tmp_path)
                tmp_files.append(tmp_path)
                success = True
                break
            except Exception as e:
                last_exc = e
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                time.sleep(backoff * attempt)
        if not success:
            print(f"[TTS] Failed chunk {idx}/{len(chunks)} lang={lang_code}: {last_exc}", file=sys.stderr)
            traceback.print_exc()
            continue
    return tmp_files

def play_file_with_fallback(path, block=True):
    if PYGAME_AVAILABLE:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception:
            pass
    if PYGAME_AVAILABLE:
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            if block:
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
            return True
        except Exception as e:
            print("[Playback] pygame failed:", e, file=sys.stderr)
    if PLAYSOUND_AVAILABLE:
        try:
            playsound(path)
            return True
        except Exception as e:
            print("[Playback] playsound failed:", e, file=sys.stderr)
    if PYDUB_AVAILABLE:
        try:
            seg = AudioSegment.from_file(path)
            pydub_play(seg)
            return True
        except Exception as e:
            print("[Playback] pydub.play failed:", e, file=sys.stderr)
    return False

def play_files_serially(paths):
    acquired = playback_lock.acquire(blocking=False)
    if not acquired:
        try:
            if PYGAME_AVAILABLE:
                pygame.mixer.music.stop()
        except Exception:
            pass
        playback_lock.acquire()
    try:
        for p in paths:
            ok = play_file_with_fallback(p, block=True)
            if not ok:
                print("[Playback] failed to play:", p, file=sys.stderr)
    finally:
        playback_lock.release()

def takecommand():
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            r.pause_threshold = 1
            try:
                audio = r.listen(source, timeout=6, phrase_time_limit=20)
            except sr.WaitTimeoutError:
                return None
        try:
            return r.recognize_google(audio, language='en-in')
        except Exception:
            return None
    except Exception as e:
        print("[Microphone] Error:", e, file=sys.stderr)
        traceback.print_exc()
        return None

# UI
BG = "#0f1724"
CARD = "#091526"
ACCENT = "#ff7a59"
ACCENT2 = "#61d4b8"
TEXT = "#e6eef6"
SUBTEXT = "#c9d7e6"

root = tk.Tk()
root.title("Colorful Multilingual Translator (No Load Audio)")
root.geometry("980x720")
root.configure(background=BG)

title_font = tkfont.Font(family="Segoe UI", size=20, weight="bold")
subtitle_font = tkfont.Font(family="Segoe UI", size=10)
label_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
text_font = tkfont.Font(family="Segoe UI", size=11)
btn_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")

header = tk.Canvas(root, height=110, highlightthickness=0)
header.pack(fill="x")
for i, color in enumerate(["#0b1220","#112033","#19344b","#214a66"]):
    header.create_rectangle(i*250, 0, (i+1)*250, 110, outline=color, fill=color)
header.create_text(30, 60, anchor="w", text="🌐 Translate Live", font=title_font, fill=TEXT)
header.create_text(30, 87, anchor="w", text="Voice/text translate • Play / Pause / Exit", font=subtitle_font, fill=SUBTEXT)

content = tk.Frame(root, bg=BG)
content.pack(fill="both", expand=True, padx=16, pady=(8,16))

# Left (Input)
left = tk.Frame(content, bg=CARD)
left.place(relx=0.02, rely=0.02, relwidth=0.46, relheight=0.75)
tk.Label(left, text="Input", bg=CARD, fg=ACCENT2, font=label_font).pack(anchor="nw", padx=12, pady=(12,6))
query_entry = tk.Text(left, height=18, wrap="word", bg="#071427", fg=TEXT, insertbackground=TEXT, font=text_font, bd=0)
query_entry.pack(padx=12, pady=(0,12), fill="both", expand=True)

def capture_voice_input_threaded():
    threading.Thread(target=capture_voice_input, daemon=True).start()

def capture_voice_input():
    query_entry.delete(1.0, tk.END)
    query_entry.insert(tk.END, "Listening...")
    query_entry.update()
    q = takecommand()
    if q is None:
        query_entry.delete(1.0, tk.END)
        update_status("Could not understand voice input.")
    else:
        query_entry.delete(1.0, tk.END)
        query_entry.insert(tk.END, q)
        update_status("Voice captured.")

input_ctrl = tk.Frame(left, bg=CARD)
input_ctrl.pack(fill="x", padx=12, pady=(0,12))
tk.Button(input_ctrl, text="🎙 Capture Voice", bg=ACCENT, fg="white", font=btn_font, bd=0, command=capture_voice_input_threaded).pack(side="left", padx=(0,8), ipadx=6, ipady=6)
tk.Button(input_ctrl, text="🧹 Clear", bg="#3a3f55", fg="white", font=btn_font, bd=0, command=lambda: query_entry.delete(1.0, tk.END)).pack(side="left", ipadx=6, ipady=6)

# Right (Output)
right = tk.Frame(content, bg=CARD)
right.place(relx=0.50, rely=0.02, relwidth=0.48, relheight=0.75)
tk.Label(right, text="Translation", bg=CARD, fg=ACCENT2, font=label_font).pack(anchor="nw", padx=12, pady=(12,6))

settings = tk.Frame(right, bg=CARD)
settings.pack(fill="x", padx=12, pady=(0,6))
tk.Label(settings, text="Target language:", bg=CARD, fg=SUBTEXT, font=subtitle_font).pack(side="left")
languages = sorted(dic.keys())
language_var = tk.StringVar(value="english")
language_dropdown = ttk.Combobox(settings, textvariable=language_var, values=languages, width=32, state="readonly", font=text_font)
language_dropdown.pack(side="left", padx=(8,0))

action_row = tk.Frame(right, bg=CARD)
action_row.pack(fill="x", padx=12, pady=(8,6))

status = tk.Label(content, text="Ready", bg=BG, fg=SUBTEXT, anchor="w", font=subtitle_font)
status.place(relx=0.02, rely=0.80, relwidth=0.96, relheight=0.06)

translated_text_entry = tk.Text(right, height=18, wrap="word", bg="#071427", fg=TEXT, insertbackground=TEXT, font=text_font, bd=0)
translated_text_entry.pack(padx=12, pady=(8,12), fill="both", expand=True)

def update_status(msg):
    status.config(text=msg)

def translate_text_threaded():
    threading.Thread(target=translate_text, daemon=True).start()

def translate_text():
    src_text = query_entry.get(1.0, tk.END).strip()
    if not src_text:
        update_status("Please enter or capture text.")
        return
    to_lang = language_var.get()
    if to_lang not in dic:
        update_status("Please select a target language.")
        return
    to_code = dic[to_lang]
    update_status("Translating...")
    translated_text_entry.delete(1.0, tk.END)
    try:
        chunks = chunk_text_for_api(src_text, MAX_TRANSLATE_CHARS)
        translated_parts = []
        for i, c in enumerate(chunks, 1):
            update_status(f"Translating chunk {i}/{len(chunks)}...")
            try:
                res = translator.translate(c, dest=to_code)
                translated_parts.append(res.text)
            except Exception as e:
                print("[Translate] chunk failed:", e, file=sys.stderr)
                traceback.print_exc()
                translated_parts.append("")
        final = " ".join(p for p in translated_parts if p).strip()
        translated_text_entry.insert(tk.END, final)
        update_status("Translation complete.")
    except Exception as e:
        print("[Translate] error:", e, file=sys.stderr)
        traceback.print_exc()
        update_status("Translation error (see console).")

def start_playback_for_text(text, lang_code):
    global is_playing
    if is_playing:
        update_status("Already playing.")
        return
    update_status("Generating speech...")
    try:
        files = generate_tts_files(text, lang_code)
        if not files:
            update_status("No audio generated.")
            return
        def runner():
            try:
                play_files_serially(files)
            finally:
                for f in files:
                    try:
                        os.remove(f)
                    except Exception:
                        pass
                update_status("Ready")
                pause_btn.config(text="⏸ Pause")
        threading.Thread(target=runner, daemon=True).start()
        update_status("Playing...")
        pause_btn.config(text="⏸ Pause")
    except Exception as e:
        print("[Playback start] error:", e, file=sys.stderr)
        traceback.print_exc()
        update_status("TTS/playback error (see console).")

def play_translation():
    text = translated_text_entry.get(1.0, tk.END).strip()
    if not text:
        update_status("No translated text to play.")
        return
    to_code = dic.get(language_var.get(), 'en')
    threading.Thread(target=start_playback_for_text, args=(text, to_code), daemon=True).start()

def pause_toggle():
    global is_paused
    if not is_playing and not (PYDUB_AVAILABLE or PYGAME_AVAILABLE):
        return
    if not is_paused:
        try:
            if PYGAME_AVAILABLE:
                pygame.mixer.music.pause()
            is_paused = True
            pause_btn.config(text="▶ Resume")
            update_status("Paused")
        except Exception as e:
            print("[Pause] failed:", e, file=sys.stderr)
            update_status("Pause failed.")
    else:
        try:
            if PYGAME_AVAILABLE:
                pygame.mixer.music.unpause()
            is_paused = False
            pause_btn.config(text="⏸ Pause")
            update_status("Playing...")
        except Exception as e:
            print("[Resume] failed:", e, file=sys.stderr)
            update_status("Resume failed.")

def stop_playback_and_cleanup():
    global is_playing, is_paused, current_tts_files
    try:
        if PYGAME_AVAILABLE:
            pygame.mixer.music.stop()
    except Exception:
        pass
    is_playing = False
    is_paused = False
    for f in current_tts_files:
        try:
            os.remove(f)
        except Exception:
            pass
    current_tts_files = []
    update_status("Stopped")

def on_close():
    stop_playback_and_cleanup()
    root.destroy()

def save_translation_audio():
    text = translated_text_entry.get(1.0, tk.END).strip()
    if not text:
        update_status("No translated text to save.")
        return
    path = filedialog.asksaveasfilename(defaultextension=".mp3", filetypes=[("MP3 files", "*.mp3")])
    if not path:
        return
    to_code = dic.get(language_var.get(), 'en')
    try:
        gTTS(text=text, lang=to_code, slow=False).save(path)
        update_status(f"Saved audio to {path}")
    except Exception:
        try:
            chunks = chunk_text_for_api(text, MAX_TTS_CHARS)
            base, ext = os.path.splitext(path)
            parts = []
            for i, c in enumerate(chunks, 1):
                part_path = f"{base}_part{i}{ext}"
                gTTS(text=c, lang=to_code, slow=False).save(part_path)
                parts.append(part_path)
            update_status(f"Saved {len(parts)} audio parts.")
        except Exception:
            print("[Save] error:", file=sys.stderr)
            traceback.print_exc()
            update_status("Save failed (see console).")

def show_supported_languages():
    top = tk.Toplevel(root)
    top.title("Supported Languages")
    top.geometry("420x520")
    top.configure(bg=CARD)
    tk.Label(top, text="Languages available (name — code)", bg=CARD, fg=TEXT, font=label_font).pack(pady=(12,6))
    frame = tk.Frame(top, bg=CARD)
    frame.pack(fill="both", expand=True, padx=12, pady=8)
    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")
    text = tk.Text(frame, wrap="none", yscrollcommand=scrollbar.set, bg="#071826", fg=TEXT, font=text_font)
    text.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=text.yview)
    for name, code in sorted(dic.items()):
        text.insert(tk.END, f"{name} — {code}\n")
    text.config(state="disabled")
    def copy_list():
        all_text = "\n".join(f"{n} — {c}" for n, c in sorted(dic.items()))
        root.clipboard_clear()
        root.clipboard_append(all_text)
        update_status("Languages copied to clipboard.")
    tk.Button(top, text="Copy to clipboard", bg=ACCENT2, fg="#062025", font=btn_font, bd=0, command=copy_list).pack(pady=(6,12))

# Buttons
translate_btn = tk.Button(action_row, text="🔄 Translate", bg=ACCENT, fg="white", font=btn_font, bd=0, command=translate_text_threaded)
translate_btn.pack(side="left", padx=(0,8), ipadx=8, ipady=8)

play_btn = tk.Button(action_row, text="🔊 Play", bg="#2b6b83", fg="white", font=btn_font, bd=0, command=lambda: threading.Thread(target=play_translation, daemon=True).start())
play_btn.pack(side="left", padx=(0,8), ipadx=8, ipady=8)

pause_btn = tk.Button(action_row, text="⏸ Pause", bg="#3a3f55", fg="white", font=btn_font, bd=0, command=pause_toggle)
pause_btn.pack(side="left", padx=(0,8), ipadx=8, ipady=8)

save_btn = tk.Button(action_row, text="💾 Save Audio", bg="#3a3f55", fg="white", font=btn_font, bd=0, command=lambda: threading.Thread(target=save_translation_audio, daemon=True).start())
save_btn.pack(side="left", padx=(0,8), ipadx=8, ipady=8)

show_langs_btn = tk.Button(action_row, text="📚 Languages", bg="#6b4cff", fg="white", font=btn_font, bd=0, command=show_supported_languages)
show_langs_btn.pack(side="left", padx=(0,8), ipadx=8, ipady=8)

exit_btn = tk.Button(action_row, text="⛔ Exit", bg="#7b2f2f", fg="white", font=btn_font, bd=0, command=on_close)
exit_btn.pack(side="left", ipadx=8, ipady=8)

root.protocol("WM_DELETE_WINDOW", on_close)
update_status(f"Ready (pydub/ffmpeg: {'OK' if PYDUB_AVAILABLE else 'No'})")
root.mainloop()
