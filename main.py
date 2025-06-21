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
    url = "http://localhost:7868/api/v1/run/100de29a-0136-45aa-89c6-47ccee483953"

    payload = {
        "input_value": text,
        "output_type": "chat",
        "input_type": "chat",
    }

    headers = {
        "Content-Type": "application/json",
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
        
        print(output)
        if output:
            try:
                # Split by actual newlines (not literal \n)
                lines = output.strip().split('\n')
                print(f"Number of lines: {len(lines)}")
                
                # Find the data row (should be the last line with actual data)
                data_line = None
                for line in lines:
                    if line.strip() and not line.startswith('|:') and line.count('|') >= 4:
                        data_line = line
                
                if data_line:
                    print(f"Data line: {data_line}")
                    # Split by | and clean up
                    parts = [p.strip() for p in data_line.split('|') if p.strip()]
                    print(f"Parts: {parts}")
                    
                    if len(parts) >= 4:
                        calls_obj = ast.literal_eval(parts[0])
                        tasks_obj = ast.literal_eval(parts[1])
                        is_call = ast.literal_eval(parts[2])
                        is_task = ast.literal_eval(parts[3])
                        
                        result = {"calls": calls_obj, "tasks": tasks_obj, "call": is_call, "task": is_task}
                        print(result)
                        
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
                                    "members": call_item.get("members", []),
                                    "date": call_item.get("date", ""),
                                    "time": call_item.get("time", "")
                                })
                                print(f"Emitted new-call: {call_item.get('name')} with members: {call_item.get('members', [])}")
                    else:
                        print(f"Not enough parts in data line: {len(parts)}")
                else:
                    print("No valid data line found")

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

    # Set up the Telegram bot
    app = (
        ApplicationBuilder()
        .token("8124160481:AAGSaxNXjDU2WCiOKBO5cnQzfTrODnDze40")
        .build()
    )
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    try:
        print("Starting Telegram bot...")
        # Initialize the bot
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # Keep the bot running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down...")
    finally:
        # Clean shutdown
        if app.updater.running:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await sio.disconnect()
        print("Disconnected from WebSocket server.")

# Запуск бота
if __name__ == "__main__":
    asyncio.run(main())
