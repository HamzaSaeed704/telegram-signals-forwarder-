from telethon import TelegramClient, events
import requests
import asyncio
import os
from PIL import Image
from dotenv import load_dotenv
from smart_crop import smart_crop
import traceback as tb
from datetime import datetime, timezone
from mail_utils import send_mail


load_dotenv()

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

N8N_WEBHOOK_TEXT = os.getenv("WEBHOOK_TEXT")
N8N_WEBHOOK_IMAGE = os.getenv("WEBHOOK_IMAGE")
N8N_WEBHOOK_IMAGE_AND_TEXT = os.getenv("WEBHOOK_IMAGE_TEXT")

def build_exception_message(title: str, desc: str, e: Exception) -> str:
    TEMPLATE = """
    {title}

    Timestamp (UTC):
    - {timestamp}

    Description:
    {desc}

    Exception Type:
    - {exc_type}

    Exception Message:
    - {exc_msg}

    Traceback:
    {traceback}
    """.strip()
    now_utc = datetime.now(timezone.utc)
    return TEMPLATE.format(
        title=title,
        timestamp=now_utc.isoformat(),
        desc=desc,
        exc_type=type(e).__name__,
        exc_msg=str(e),
        traceback=tb.format_exc()
    )


# Safely parse comma-separated IDs into a list of integers
try:
    TEXT_ONLY_SOURCES = list(map(int, filter(None, os.getenv("TEXT_ONLY", "").split(","))))
    TEXT_AND_IMAGE_SOURCES = list(map(int, filter(None, os.getenv("TEXT_AND_IMAGE", "").split(","))))
    IMAGE_ONLY_SOURCES = list(map(int, filter(None, os.getenv("IMAGE_ONLY", "").split(","))))
except ValueError as e:
    print(f"FATAL ERROR: Failed to parse chat IDs. Check your .env file for invalid characters or formats: {e}")
    exit(1)

ALL_SOURCES = TEXT_ONLY_SOURCES + TEXT_AND_IMAGE_SOURCES + IMAGE_ONLY_SOURCES

# Initialize Telethon Client
client = TelegramClient("Ali_Session", api_id, api_hash)

DOWNLOAD_FOLDER = "./downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Global State Management
PROCESSED_MESSAGES = set()
ALBUM_CACHE = {}
ALBUM_LOCK = asyncio.Lock()


async def delete_after_forward(files, delay=30):
    """Deletes files after a delay to ensure the webhook has time to process them."""
    await asyncio.sleep(delay)
    for f in files:
        try:
            # Delete the cropped image (if it exists)
            if "_cropped.jpg" in f:
                os.remove(f)
                original_path = f.replace("_cropped.jpg", ".jpg")
                if os.path.exists(original_path):
                    os.remove(original_path)
                    print(f"[🗑] Deleted original: {original_path}")
            # Delete any remaining file paths
            elif os.path.exists(f):
                os.remove(f)

            print(f"[🗑] Deleted: {f}")
        except Exception as e:
            pass


def crop_image(path):
    """Crops an image vertically (removes 15% from top and bottom).""" # Only works for JPEGs.Mexc
    try:
        # Check if the file is a JPEG. If it's a temp file, Telethon names it without extension
        # The preceding block in the handler will ensure it's converted to .jpg if possible.
        img = Image.open(path)
        w, h = img.size

        # Define crop boundaries (remove 15% top and 15% bottom)
        top = int(h * 0.15)
        bottom = int(h * 0.85)

        crop = img.crop((0, top, w, bottom))
        
        # Use a unique name for the cropped version
        new_path = path.replace(".jpg", "_cropped.jpg") if path.endswith(".jpg") else path + "_cropped.jpg"
        
        # Save as JPEG with high quality
        crop.save(new_path, "JPEG", quality=95)
        return new_path
    except Exception as e:
        print(f"[⚠] Crop failed for {path}: {e}")
        # If crop fails, return the original path so the image is still forwarded
        return path

def post_files(url, data_dict, paths):
    """Posts data and files to the specified URL (n8n webhook)."""
    files = {}
    opened = []

    try:
        for i, p in enumerate(paths):
            if not os.path.exists(p):
                print(f"[⚠] File not found: {p}. Skipping.")
                continue

            f = open(p, "rb")
            opened.append(f)
            # Send all images under image1, image2, etc.
            files[f"image{i+1}"] = (os.path.basename(p), f, "image/jpeg")

        if not files:
            print("[⚠] No files were successfully opened for posting.")
            return None
        try:
            resp = requests.post(url, data=data_dict, files=files, timeout=60)
            return resp
        except Exception as e:
            msg = build_exception_message(
            title="[Webhook POST] Failed",
                desc=f"Webhook URL: {url}\nData: {data_dict}\nFiles: {paths}",
                e=e
            )
            send_mail(heading="[Webhook POST] Exception", message=msg)
    finally:
        for f in opened:
            f.close()



async def route_message(source_id, text, images):
    """Determines the correct webhook based on source ID and message content."""
    
    # Clean up text: remove newlines/spaces if there is no actual content
    text = text.strip() if text else ""
    
    print(f"\n📡 ROUTING FROM {source_id} (Text: {bool(text)}, Images: {len(images)})")

    # TEXT ONLY
    if source_id in TEXT_ONLY_SOURCES:
        print("➡ RULE: TEXT ONLY")
        if text:
            requests.post(N8N_WEBHOOK_TEXT, data={"group": source_id, "text": text})
            print(f"[SENT → TEXT WORKFLOW]")
        # Schedule cleanup only if there were images (e.g., in an album mix-up)
        if images:
            asyncio.create_task(delete_after_forward(images))
        return

    # IMAGE ONLY
    if source_id in IMAGE_ONLY_SOURCES:
        print("➡ RULE: IMAGE ONLY")
        if images:
            resp = post_files(N8N_WEBHOOK_IMAGE, {"group": source_id, "text": text}, images)
            print(f"[SENT → IMAGE WORKFLOW]")
            asyncio.create_task(delete_after_forward(images))
        else:
            # If image-only source sends text, log it but don't forward unless needed
            if text:
                print("[INFO] Text-only message received in IMAGE_ONLY source. Dropped.")
        return

    # TEXT + IMAGE
    if source_id in TEXT_AND_IMAGE_SOURCES:
        print("➡ RULE: TEXT + IMAGE")
        data = {"group": source_id, "text": text}

        if images:
            resp = post_files(N8N_WEBHOOK_IMAGE_AND_TEXT, data, images)
            print(f"[SENT → TEXT+IMAGE WORKFLOW]", resp)
            asyncio.create_task(delete_after_forward(images))
        elif text:
            # Send text-only if no images are present but text is
            requests.post(N8N_WEBHOOK_IMAGE_AND_TEXT, data)
            print("[SENT → TEXT+IMAGE WORKFLOW (TEXT ONLY)]")
        
        return
    
    # Fallback for unexpected source IDs
    print(f"[INFO] Source ID {source_id} not found in any source list. Message ignored.")


async def album_finalize(album_id):
    """Waits a short time for all parts of an album to arrive, then routes it."""
    try:
        try:
            # Wait a short time (1 second) to gather all album parts
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            # If a new part arrives, the task is cancelled and restarted
            return

        async with ALBUM_LOCK:
            content = ALBUM_CACHE.pop(album_id, None)

        if content:
            # Clean up text from potential multiple messages
            cleaned_text = content["text"].strip()
            
            await route_message(content["source"], cleaned_text, content["images"])
    except Exception as e:
        msg = build_exception_message(
            title="[Album Finalize] Failed",
            desc=f"Error finilizing album id {album_id}",
            e=e
        )
        send_mail(message=msg, heading="[Album Finalize] Exception")

async def main():
    print("\n🔥 Starting Telegram Client …\n")
    
    # 🚨 CRITICAL FIX: The entire Telegram session must be inside this block 
    # to maintain connection for the listener.
    async with client: 
        print("🔍 Validating chat access:")
        # Validation Loop (runs while client is connected)
        for cid in ALL_SOURCES:
            try:
                entity = await client.get_entity(cid)
                print(f"✔ {cid} → {entity.title} ({'Channel' if entity.broadcast else 'Group'})")
            except Exception as e:
                print(f"❌ ERROR: Cannot access {cid}. Please check the ID in your .env file. Details: {e}")
                msg = build_exception_message(
                    title="[[Telegram Init] Failed to access chat]",
                    desc=f"Cannot access chat ID {cid}",
                    e=e
                    )
                send_mail("[Telegram Init] Failed to access chat",message=msg)
        print("\n✅ Validation complete. Listening to messages...")


        # Event Handler Definition (MUST be inside the connected session)
        @client.on(events.NewMessage(chats=ALL_SOURCES))
        async def handler(event):
            chat_id = event.chat_id
            msg_id = event.message.id
            key = f"{chat_id}:{msg_id}"

            # Prevent processing the same message twice (common in albums)
            if key in PROCESSED_MESSAGES:
                return
            PROCESSED_MESSAGES.add(key)

            text = (event.raw_text or "").strip()
            media = event.message.media
            album_id = getattr(event.message, "grouped_id", None)
            images = []

            if media:
                print("Image Recived in ", chat_id)
            
            # DOWNLOAD MEDIA
            if media:
                path = None
                try:
                    # Download media to the designated folder
                    path = await event.download_media(DOWNLOAD_FOLDER)
                except Exception as e:
                    print(f"[⚠] Download failed for message {msg_id}: {e}")
                
                if path:
                    # Convert to JPG if not already (Telethon uses temp filenames often)
                    is_jpeg = path.lower().endswith(('.jpg', '.jpeg'))
                    if not is_jpeg:
                        try:
                            img = Image.open(path)
                            new = path + ".jpg"
                            img.save(new, "JPEG", quality=95)
                            
                            # Remove original file if it was converted (e.g., for PNGs)
                            if os.path.exists(path):
                                os.remove(path)
                                
                            path = new
                        except Exception as e:
                            print(f"[⚠] Conversion to JPG failed: {e}")
                            # If conversion fails, keep the original path if it exists
                            if not is_jpeg:
                                pass # This will likely fail the crop/post too
                            
                    if path.endswith(".jpg"): # Only proceed if we have a JPG path
                        # cropped = crop_image(path)
                        if chat_id in IMAGE_ONLY_SOURCES:
                            cropped = await asyncio.to_thread(smart_crop, path)
                            if cropped is not None:
                                images.append(cropped)
                                print(f"[📥 IMAGE DOWNLOADED] {cropped}")
                            else:
                                print("Garbage Image Found Don't Send to Webhook.")
                                #if images: await asyncio.create_task(delete_after_forward(images))
                                os.remove(path)
                                text = None

                        else:
                            images.append(path)


            # # ALBUM LOGIC (Cache parts and set a timer to finalize)
            # if album_id:
            #     async with ALBUM_LOCK:
            #         if album_id not in ALBUM_CACHE:
            #             ALBUM_CACHE[album_id] = {
            #                 "source": chat_id,
            #                 "text": "",
            #                 "images": [],
            #                 "task": None
            #             }

            #         # Append text (caption is only on one message, usually the first)
            #         if text:
            #             # Only add text if it's new, to prevent duplication from multiple captions
            #             if text not in ALBUM_CACHE[album_id]["text"]:
            #                  ALBUM_CACHE[album_id]["text"] += "\n" + text

            #         if images:
            #             ALBUM_CACHE[album_id]["images"].extend(images)

            #         # Cancel old finalize task and create a new one to extend the timer
            #         if ALBUM_CACHE[album_id]["task"]:
            #             ALBUM_CACHE[album_id]["task"].cancel()

            #         ALBUM_CACHE[album_id]["task"] = asyncio.create_task(album_finalize(album_id))
            #     return

            # SINGLE MESSAGE (Route immediately)
            if text or images:
                await route_message(chat_id, text, images)

        # 🚨 CRITICAL FIX: This MUST be the last line inside the 'async with client:' block
        await client.run_until_disconnected()

if __name__ == "__main__":
    # Ensure all required webhooks are set before starting
    if not all([N8N_WEBHOOK_TEXT, N8N_WEBHOOK_IMAGE, N8N_WEBHOOK_IMAGE_AND_TEXT]):
        print("FATAL ERROR: One or more webhook URLs are missing in the .env file.")
        exit(1)

    asyncio.run(main())