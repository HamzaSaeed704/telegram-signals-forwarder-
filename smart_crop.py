import cv2
from openai import OpenAI
from dotenv import load_dotenv
import os
import base64
from mail_utils import send_mail
import traceback
from datetime import datetime, timezone

LOGO_HEIGHT = 120
TARGET_HEIGHT = 600

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
    
def categorize_image(img_path:str):
    image_b64 = encode_image(img_path)

    prompt = """
Role: Expert Image Classifier for Crypto Trading Interfaces.

Task: Identify if the image is a native, digital screenshot of a specific trading platform's PNL/Position card.

Platform Identifiers:
- "futurebinance": Look for "Binance Futures" logo, "ROE" percentage in large font, "Symbol/USDT Perpetual" text, or the "Long/Short" indicators in green/red blocks.
- "mexc": Look for "Profit Rate" (instead of ROE), "Isolated/Cross" margins, and the specific MEXC teal/green branding or logo.
- "xbt": Look for PrimeXBT dashboard markers, "Trade P/L" labels, and its distinct dark-grey/blue interface.

Classification Rules:
1. ONLY return a platform name if the image shows a clear, high-quality digital capture of the PNL/Position area.
2. Return "none" ONLY if the image is a physical photograph (showing hands, bezels, or room glare) or if it is completely unrelated to trading.
3. Be permissive with digital screenshots: if it is a clear digital capture, classify it based on the UI layout even if it is cropped.

Output:
- Return ONLY one of these strings: "mexc", "futurebinance", "xbt", or "none".
- No explanations. No markdown formatting. No extra text.
    """
    
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (prompt)
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{image_b64}"
                    }
                ]
            }
        ]
    )

    return response.output_text



def cropt_mexc(img):
    h, w = img.shape[:2]

    top = int(h * 0.15)
    bottom = int(h * 0.88)

    cropped = img[top:bottom, :]
    return cropped

def cropt_fb(img):
    h, w = img.shape[:2]
    scale = TARGET_HEIGHT / h
    img = cv2.resize(
        img, 
        (round(w * scale), TARGET_HEIGHT), interpolation=cv2.INTER_AREA
    )
    h, w = img.shape[:2]
    top = min(LOGO_HEIGHT + int(0.05 * h), h)
    bottom = min(LOGO_HEIGHT + int(0.53 * h), h)
    # cv2.rectangle(img, (0, LOGO_HEIGHT), (w, LOGO_HEIGHT+287), (0, 0, 255), 2)
    return img[top:bottom, 0:w]

def cropt_xbt(img):
    h, w = img.shape[:2]
    scale = TARGET_HEIGHT / h
    img = cv2.resize(
        img, 
        (round(w * scale), TARGET_HEIGHT), interpolation=cv2.INTER_AREA
    )
    h, w = img.shape[:2]
    top = 0
    bottom = int(h)        # similar to h - 65
    left = 0
    right = int(w * 0.70)
    # cv2.rectangle(img, (0, 0), (483, h-50), (0, 0, 255), 2)
    return img[top:bottom, left:right]
    # cv2.rectangle(img, (0, LOGO_HEIGHT), (w, LOGO_HEIGHT+287), (0, 0, 255), 2)
    # return img[LOGO_HEIGHT:LOGO_HEIGHT + 256, 0:w]

def smart_crop(img_path:str):
    cropt_img = None
    try:
        img_orignal = cv2.imread(img_path)
        try:
            result = categorize_image(img_path)
        except Exception as e:
            now_utc = datetime.now(timezone.utc)
            message = f"""
An exception occurred while categorizing an image using OpenAI.

Timestamp (UTC):
- {now_utc.isoformat()}

Function:
- categorize_image

Image Path:
- {img_path}

Exception Type:
- {type(e).__name__}

Exception Message:
- {str(e)}

Traceback:
{traceback.format_exc()}
"""
            send_mail("[AI][Image Categorization] OpenAI API Failure",message )
        try:
            if result == "mexc":
                cropt_img = cropt_mexc(img_orignal)
            elif result == "futurebinance":
                cropt_img = cropt_fb(img_orignal)
            elif result == "xbt":
                cropt_img = cropt_xbt(img_orignal)
            else:
                return None
        except Exception as e:
            now_utc = datetime.now(timezone.utc)
            message = f"""
An exception occurred while cropping an image based on provider result.

Timestamp (UTC):
- {now_utc.isoformat()}

Provider Result:
- {result}

Image Reference:
- img_orignal (object in memory)

Crop Function:
- {(
        "cropt_mexc" if result == "mexc" else
        "cropt_fb" if result == "futurebinance" else
        "cropt_xbt" if result == "xbt" else
        "unknown"
    )}

Exception Type:
- {type(e).__name__}

Exception Message:
- {str(e)}

Traceback:
{traceback.format_exc()}
"""
            send_mail("[Image Crop][Provider Handler] Failure")
        if cropt_img is not None:
            new_path = img_path.replace(".jpg", "_cropped.jpg") if img_path.endswith(".jpg") else img_path + "_cropped.jpg"
            cv2.imwrite(new_path, cropt_img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            return new_path
        return None
    except Exception as e:
        print(f"[⚠] Crop failed for {img_path}: {e}")
        return None
    
if __name__ == "__main__":
    print(smart_crop("img/fb3.jpg"))