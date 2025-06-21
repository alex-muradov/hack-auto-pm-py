import requests
import whisper
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import re
import ast
import json
from typing import List, Dict, Any

# Загружаем модель Whisper один раз
model = whisper.load_model(
    "large"
)  # или "small", "medium", "large" — зависит от точности и скорости

def parse_langflow_response(response_text: str) -> List[Dict[str, Any]]:

    pattern = r"(\[\{.*?\}\])"
    matches = re.findall(pattern, response_text, re.DOTALL)
    
    all_objects = []
    for match in matches:
        try:
            # The matched string is a Python literal, so we use ast.literal_eval
            parsed_list = ast.literal_eval(match)
            if isinstance(parsed_list, list):
                all_objects.extend(parsed_list)
        except (ValueError, SyntaxError) as e:
            print(f"Could not parse a matched part of the response: {match}")
            print(f"Error: {e}")
            
    return all_objects

# Обработка голосовых
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    # Скачиваем файл
    ogg_path = "voice_{voice.file_id}.ogg"
    mp3_path = ogg_path.replace(".ogg", ".mp3")
    await file.download_to_drive(ogg_path)

    # Конвертация .ogg → .mp3 (или .wav)
    import ffmpeg

    ffmpeg.input(ogg_path).output(mp3_path).run(overwrite_output=True)

    # Распознаём текст с Whisper
    result = model.transcribe(mp3_path)
    text = result["text"]

    # Удалим временные файлы
    os.remove(ogg_path)
    os.remove(mp3_path)

    await update.message.reply_text(f"🗣 Распознанный текст:\n{text}")

    # The complete API endpoint URL for this flow
    url = "https://api.langflow.astra.datastax.com/lf/b4828243-d5e3-41b7-90c9-8200dfe14113/api/v1/run/9968a0f4-7598-4543-b709-01539b95d734"

    payload = {
        "input_value": text,  # The input value to be processed by the flow
        "output_type": "chat",  # Specifies the expected output format
        "input_type": "chat",  # Specifies the input format
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer AstraCS:UegUmCocfwshlqlcYcvUzvoc:327d8f2ba67d8b451140b22fd8c04c13283294a855cab146f3aacfca7b514ef0",
    }

    try:
        # Send API request
        response = requests.request("POST", url, json=payload, headers=headers)
        response.raise_for_status()  # Raise exception for bad status codes
        response_text = response.json().data
        print(parse_langflow_response(response_text))

    except requests.exceptions.RequestException as e:
        print(f"Error making API request: {e}")
    except ValueError as e:
        print(f"Error parsing response: {e}")


# Запуск бота
if __name__ == "__main__":
    app = (
        ApplicationBuilder()
        .token("8124160481:AAGSaxNXjDU2WCiOKBO5cnQzfTrODnDze40")
        .build()
    )
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.run_polling()
