import tkinter as tk
from tkinter import ttk, messagebox
import speech_recognition as sr
from googletrans import Translator
from gtts import gTTS
from pygame import mixer

# Initialize pygame mixer
mixer.init()

# Dictionary of supported languages
dic = {
    'afrikaans': 'af', 'albanian': 'sq', 'amharic': 'am', 'arabic': 'ar',
    'armenian': 'hy', 'azerbaijani': 'az', 'basque': 'eu', 'belarusian': 'be',
    'bengali': 'bn', 'bosnian': 'bs', 'bulgarian': 'bg', 'catalan': 'ca',
    'cebuano': 'ceb', 'chichewa': 'ny', 'chinese (simplified)': 'zh-cn',
    'chinese (traditional)': 'zh-tw', 'croatian': 'hr', 'czech': 'cs',
    'danish': 'da', 'dutch': 'nl', 'english': 'en', 'esperanto': 'eo',
    'estonian': 'et', 'filipino': 'tl', 'finnish': 'fi', 'french': 'fr',
    'german': 'de', 'greek': 'el', 'gujarati': 'gu', 'hindi': 'hi',
    'hungarian': 'hu', 'icelandic': 'is', 'indonesian': 'id', 'italian': 'it',
    'japanese': 'ja', 'kannada': 'kn', 'korean': 'ko', 'latin': 'la',
    'latvian': 'lv', 'lithuanian': 'lt', 'malayalam': 'ml', 'marathi': 'mr',
    'nepali': 'ne', 'norwegian': 'no', 'persian': 'fa', 'polish': 'pl',
    'portuguese': 'pt', 'punjabi': 'pa', 'romanian': 'ro', 'russian': 'ru',
    'spanish': 'es', 'swahili': 'sw', 'swedish': 'sv', 'tamil': 'ta',
    'telugu': 'te', 'thai': 'th', 'turkish': 'tr', 'ukrainian': 'uk',
    'urdu': 'ur', 'vietnamese': 'vi', 'zulu': 'zu', 'assamese': 'as'
}

# Function to speak text
def speak(text, lang="en"):
    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save("output_voice.mp3")
        mixer.music.load("output_voice.mp3")
        mixer.music.play()
    except Exception as e:
        messagebox.showerror("Error", f"Speech error: {e}")

# Speech recognition
def takecommand():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        query_entry.delete(1.0, tk.END)
        query_entry.insert(tk.END, "Listening...")
        query_entry.update()

        r.pause_threshold = 1
        audio = r.listen(source)

    try:
        query = r.recognize_google(audio, language='en-in')
        return query
    except Exception:
        return None

# Capture voice input
def capture_voice_input():
    query = takecommand()
    if query:
        query_entry.delete(1.0, tk.END)
        query_entry.insert(tk.END, query)
    else:
        messagebox.showwarning("Warning", "Could not understand voice input.")

# Translate text
def translate_text():
    query = query_entry.get(1.0, tk.END).strip()
    if not query:
        messagebox.showwarning("Warning", "Please enter or speak text first.")
        return

    to_lang = language_var.get()
    if to_lang not in dic:
        messagebox.showwarning("Warning", "Please select a valid target language.")
        return

    to_lang_code = dic[to_lang]
    translator = Translator()

    try:
        text_to_translate = translator.translate(query, dest=to_lang_code)
        translated_text = text_to_translate.text

        translated_text_entry.delete(1.0, tk.END)
        translated_text_entry.insert(tk.END, translated_text)

        speak(translated_text, to_lang_code)
    except Exception as e:
        messagebox.showerror("Error", f"Translation error: {e}")

# Exit program
def exit_program():
    root.destroy()

# Tkinter GUI
root = tk.Tk()
root.title("Real-Time Voice Translator")

query_label = tk.Label(root, text="Enter text or use voice input:")
query_label.pack()

query_entry = tk.Text(root, height=3, width=50)
query_entry.pack()

voice_input_button = tk.Button(root, text="Capture Voice Input", command=capture_voice_input)
voice_input_button.pack()

language_label = tk.Label(root, text="Select destination language:")
language_label.pack()

languages = sorted(dic.keys())
language_var = tk.StringVar()
language_var.set("english")
language_dropdown = ttk.Combobox(root, textvariable=language_var, values=languages)
language_dropdown.pack()

translate_button = tk.Button(root, text="Translate", command=translate_text)
translate_button.pack()

translated_text_label = tk.Label(root, text="Translated Text:")
translated_text_label.pack()

translated_text_entry = tk.Text(root, height=3, width=50)
translated_text_entry.pack()

exit_button = tk.Button(root, text="Exit", command=exit_program)
exit_button.pack()

root.mainloop()
