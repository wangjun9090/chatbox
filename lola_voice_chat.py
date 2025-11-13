# lola_voice_chat.py
# Senior-friendly, tender voice, natural interruption, full Bible reading
import os
import re
import requests
import speech_recognition as sr
import pyttsx3
import threading
import queue
import time
from dotenv import load_dotenv

# -------------------------------------------------
# 1. Load HF token
# -------------------------------------------------
load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    raise RuntimeError("HF_TOKEN not found in .env")

# -------------------------------------------------
# 2. HF Inference
# -------------------------------------------------
BASE_URL = "https://router.huggingface.co/v1/chat/completions"
MODEL_ID = "meta-llama/Meta-Llama-3-8B-Instruct"
headers = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

def ask_llama(messages, max_tokens=2048, temperature=0.7):
    payload = {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False
    }
    try:
        resp = requests.post(BASE_URL, headers=headers, json=payload, timeout=180)
        if resp.status_code != 200:
            print(f"API Error {resp.status_code}: {resp.text}")
            return None
        data = resp.json()
        if "choices" not in data or not data["choices"]:
            print("No response from model")
            return None
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Request failed: {e}")
        return None

# -------------------------------------------------
# 3. Sentence splitter
# -------------------------------------------------
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

def split_into_sentences(text):
    if not text:
        return []
    sentences = []
    current_pos = 0
    for match in SENTENCE_END.finditer(text):
        sentence = text[current_pos:match.end()].strip()
        if sentence:
            sentences.append(sentence)
        current_pos = match.end()
    final = text[current_pos:].strip()
    if final:
        sentences.append(final)
    return sentences if sentences else [text.strip()]

# -------------------------------------------------
# 4. Speech Recognition Setup
# -------------------------------------------------
main_recognizer = sr.Recognizer()
main_recognizer.energy_threshold = 4000
main_recognizer.dynamic_energy_threshold = True
main_recognizer.pause_threshold = 1.8  # Gentle pause for seniors

interrupt_recognizer = sr.Recognizer()
interrupt_recognizer.energy_threshold = 5000
interrupt_recognizer.dynamic_energy_threshold = False
interrupt_recognizer.pause_threshold = 0.8

try:
    main_mic = sr.Microphone(device_index=0)
    interrupt_mic = sr.Microphone(device_index=0)
except:
    main_mic = sr.Microphone()
    interrupt_mic = sr.Microphone()

# -------------------------------------------------
# 5. TTS: TENDER, SOFT, LOVING FEMALE VOICE
# -------------------------------------------------
tts_queue = queue.Queue()
interrupt_flag = threading.Event()
is_speaking = threading.Event()

def init_tts_engine():
    try:
        engine = pyttsx3.init()
        
        # SLOWER, SOFTER, WARMER
        engine.setProperty('rate', 135)      # Slower = more tender
        engine.setProperty('volume', 0.85)   # Gentle volume

        voices = engine.getProperty('voices')
        preferred = None
        for v in voices:
            name = v.name.lower()
            if 'zira' in name:
                preferred = v.id
                print(f"Voice: {v.name} (Zira - warm & clear)")
                break
            elif 'hazel' in name:
                preferred = v.id
                print(f"Voice: {v.name} (Hazel - soft & kind)")
                break
            elif any(x in name for x in ['susan', 'catherine', 'samantha', 'heera']):
                preferred = v.id
                print(f"Voice: {v.name} (soft female)")
                break

        if preferred:
            engine.setProperty('voice', preferred)
        else:
            print(f"Voice: {voices[0].name} (fallback)")

        return engine
    except Exception as e:
        print(f"TTS init error: {e}")
        return pyttsx3.init()

def tts_worker():
    engine = init_tts_engine()
    engine.startLoop(False)
    try:
        while True:
            sentence = tts_queue.get()
            if sentence is None:
                break
            if interrupt_flag.is_set():
                tts_queue.task_done()
                continue

            is_speaking.set()
            try:
                engine.say(sentence)
                start = time.time()
                while engine.isBusy() and (time.time() - start) < 25:
                    if interrupt_flag.is_set():
                        engine.stop()
                        break
                    engine.iterate()
                    time.sleep(0.005)
                if engine.isBusy():
                    engine.stop()
            finally:
                is_speaking.clear()
            tts_queue.task_done()
    finally:
        engine.endLoop()

tts_thread = threading.Thread(target=tts_worker, daemon=True)
tts_thread.start()

def speak(sentence):
    if sentence and sentence.strip():
        print(f"Lola: {sentence}")
        tts_queue.put(sentence)

def clear_speech_queue():
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
            tts_queue.task_done()
        except:
            break

# -------------------------------------------------
# 6. NATURAL INTERRUPTION PHRASES (Senior-friendly)
# -------------------------------------------------
INTERRUPT_PHRASES = [
    'stop', 'halt', 'pause', 'wait', 'hold on',
    'that\'s enough', 'okay thank you', 'you can pause now',
    'enough', 'okay stop', 'alright stop', 'thank you',
    'i\'ve heard enough', 'that will do', 'no more',
    'please stop', 'can you stop', 'let me think'
]

def check_for_interrupt():
    try:
        with interrupt_mic as source:
            interrupt_recognizer.adjust_for_ambient_noise(source, duration=0.1)
            audio = interrupt_recognizer.listen(source, phrase_time_limit=2.0, timeout=0.8)
            try:
                text = interrupt_recognizer.recognize_google(audio).lower(). agricultura().strip()
                print(f"Detected: '{text}'")
                if any(phrase in text for phrase in INTERRUPT_PHRASES):
                    print("MATCHED interrupt phrase!")
                    return True
                return False
            except sr.UnknownValueError:
                return False
    except sr.WaitTimeoutError:
        return False
    except Exception as e:
        if "timeout" not in str(e).lower():
            print(f"Interrupt error: {e}")
        return False

def interrupt_monitor():
    while not interrupt_flag.is_set():
        if not is_speaking.is_set():
            time.sleep(0.1)
            continue
        if check_for_interrupt():
            interrupt_flag.set()
            clear_speech_queue()
            print("Stopping speech gracefully...")
            return
        time.sleep(0.12)

# -------------------------------------------------
# 7. Main Loop – WARM & ENGAGING
# -------------------------------------------------
def main():
    print("\n" + "="*70)
    print("  LOLA - Your Gentle Companion")
    print("="*70)
    print("\nInstructions:")
    print("  • Speak naturally — I’ll wait for you to finish")
    print("  • Say 'That's enough' or 'Okay, thank you' to pause me")
    print("  • Say 'exit' to say goodbye\n")

    # WARM, TENDER WELCOME FOR SENIORS
    welcome = (
        "Hello, dear. I'm Lola, your gentle friend. "
        "I'm here to help with anything on your mind — "
        "whether it's reading from the Bible, answering a question, "
        "or just keeping you company. "
        "Take your time… I'm listening."
    )
    speak(welcome)

    conversation = [
        {"role": "system", "content": (
            "You are Lola, a warm, patient, and tender assistant for seniors. "
            "Speak slowly, clearly, and kindly. "
            "When reading Bible chapters, give the COMPLETE text with verse numbers. "
            "Never summarize. Always be thorough, gentle, and caring."
        )}
    ]

    silence_count = 0

    while True:
        print("\n" + "-"*70)
        print("Listening for your voice…")

        try:
            with main_mic as source:
                main_recognizer.adjust_for_ambient_noise(source, duration=0.6)
                audio = main_recognizer.listen(source, phrase_time_limit=40, timeout=18)
        except sr.WaitTimeoutError:
            silence_count += 1
            if silence_count >= 3:
                speak("I'm still here, whenever you're ready.")
                silence_count = 0
            continue
        except Exception as e:
            print(f"Mic error: {e}")
            continue

        silence_count = 0
        try:
            user_text = main_recognizer.recognize_google(audio).strip()
        except sr.UnknownValueError:
            print("I didn't quite catch that… could you repeat?")
            continue
        except Exception as e:
            print(f"Recognition error: {e}")
            continue

        if not user_text:
            continue

        print(f"You said: {user_text}")

        if any(word in user_text.lower() for word in ['exit', 'quit', 'goodbye', 'bye bye']):
            speak("Take care, dear. I'll be here if you need me again.")
            break

        long_request = any(phrase in user_text.lower() for phrase in [
            'read john', 'read chapter', 'read psalm', 'read genesis',
            'read matthew', 'read luke', 'read romans', 'bible chapter',
            'entire chapter', 'full chapter', 'complete chapter'
        ])

        conversation.append({"role": "user", "content": user_text})

        try:
            print("Thinking gently…")
            max_tokens = 4096 if long_request else 300
            answer = ask_llama(conversation, max_tokens=max_tokens)

            if not answer:
                speak("I'm sorry, dear, I couldn't reach the answer just now. Shall we try again?")
                conversation.pop()
                continue

            conversation.append({"role": "assistant", "content": answer})

            sentences = split_into_sentences(answer)
            print(f"Response: {len(sentences)} parts to share…")

            interrupt_flag.clear()
            monitor = threading.Thread(target=interrupt_monitor, daemon=True)
            monitor.start()

            interrupted = False
            for i, sentence in enumerate(sentences):
                if interrupt_flag.is_set():
                    interrupted = True
                    break

                speak(sentence)

                start = time.time()
                while is_speaking.is_set() and not interrupt_flag.is_set():
                    if time.time() - start > 28:
                        break
                    time.sleep(0.06)

                if interrupt_flag.is_set():
                    interrupted = True
                    break

                time.sleep(0.15)  # Gentle pause

            if interrupted:
                speak("Of course, dear. I've paused. What would you like to do next?")
                while is_speaking.is_set():
                    time.sleep(0.1)
            else:
                print("Finished sharing.")

            if len(conversation) > 11:
                conversation = [conversation[0]] + conversation[-10:]

        except Exception as e:
            print(f"Error: {e}")
            speak("Oh dear, something went wrong. Let’s try again.")

    print("\nShutting down gently…")
    tts_queue.put(None)
    tts_thread.join(timeout=5)

if __name__ == "__main__":
    main()
