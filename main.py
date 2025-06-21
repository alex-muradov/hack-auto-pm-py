import requests
import whisper
import os
import re
import ast
import json
import asyncio
import time
import socketio
from typing import List, Dict, Any
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# Socket.IO Client - connects to your existing WebSocket server
sio = socketio.AsyncClient()
SOCKET_URL = "http://localhost:3001" # Your existing WebSocket server

# Загружаем модель Whisper один раз
model = whisper.load_model("large")

# Обработка голосовых
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    # Скачиваем файл
    ogg_path = f"voice_{voice.file_id}.ogg"
    mp3_path = ogg_path.replace(".ogg", ".mp3")
    await file.download_to_drive(ogg_path)

    # Конвертация .ogg → .mp3
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
        "input_value": text,
        "output_type": "chat",
        "input_type": "chat",
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer AstraCS:UegUmCocfwshlqlcYcvUzvoc:327d8f2ba67d8b451140b22fd8c04c13283294a855cab146f3aacfca7b514ef0",
    }

    try:
        response = requests.request("POST", url, json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        output = None
        if "outputs" in data and data["outputs"]:
            first_output = data["outputs"][0]
            if "outputs" in first_output and first_output["outputs"]:
                second_output = first_output["outputs"][0]
                if "results" in second_output and "message" in second_output.get("results", {}):
                    message_data = second_output["results"]["message"].get("data")
                    if message_data and "text" in message_data:
                        output = message_data["text"]
        
        if output:
            try:
                lines = output.strip().split('\\n')
                if len(lines) >= 3:
                    parts = [p.strip() for p in lines[2].split('|') if p.strip()]
                    if len(parts) == 4:
                        calls_obj = ast.literal_eval(parts[0])
                        tasks_obj = ast.literal_eval(parts[1])
                        is_call = ast.literal_eval(parts[2])
                        is_task = ast.literal_eval(parts[3])
                        
                        result = {"calls": calls_obj, "tasks": tasks_obj, "call": is_call, "task": is_task}
                        pretty_output = json.dumps(result, indent=2, ensure_ascii=False)
                        await update.message.reply_text(f"Полученный объект:\n{pretty_output}")

                        if is_task and isinstance(tasks_obj, list):
                            for task_item in tasks_obj:
                                await sio.emit("new-task", {
                                    "id": int(time.time() * 1000),
                                    "text": task_item.get("title", "No Title"),
                                    "status": "todo",
                                    "priority": task_item.get("priority", "medium").lower()
                                })
                                print(f"Emitted new-task: {task_item.get('title')}")

                        if is_call and isinstance(calls_obj, list):
                            for call_item in calls_obj:
                                await sio.emit("new-call", {
                                    "name": call_item.get("name", "No Name"),
                                    "status": call_item.get("status", "No Status"),
                                    "priority": call_item.get("priority", "medium").lower()
                                })
                                print(f"Emitted new-call: {call_item.get('name')}")

            except (ValueError, SyntaxError, IndexError) as e:
                print(f"Error parsing string from table: {e}")
                await update.message.reply_text(f"Ответ от API (ошибка парсинга):\n{output}")
        else:
            await update.message.reply_text("Не удалось извлечь сообщение из ответа.")

    except requests.exceptions.RequestException as e:
        print(f"Error making API request: {e}")
    except ValueError as e:
        print(f"Error parsing response: {e}")

async def main():
    # Connect to your existing WebSocket server on port 3001
    try:
        await sio.connect(SOCKET_URL)
        print(f"Connected to WebSocket server at {SOCKET_URL}")
    except socketio.exceptions.ConnectionError as e:
        print(f"Failed to connect to WebSocket server: {e}")
        return

    # Set up and run the Telegram bot
    app = (
        ApplicationBuilder()
        .token("8124160481:AAGSaxNXjDU2WCiOKBO5cnQzfTrODnDze40")
        .build()
    )
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    try:
        print("Starting Telegram bot...")
        await app.run_polling()
    finally:
        await sio.disconnect()
        print("Disconnected from WebSocket server.")

# Запуск бота
if __name__ == "__main__":
    asyncio.run(main())
