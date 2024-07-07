import logging
import os
import re
import sys
import csv
if os.getenv('API_ENV') != 'production':
    from dotenv import load_dotenv

    load_dotenv()


from fastapi import FastAPI, HTTPException, Request
from datetime import datetime
from linebot.models import (
    TextSendMessage,
    QuickReply,
    QuickReplyButton,
    MessageAction
)
from linebot.v3.webhook import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
    URIAction,
    ShowLoadingAnimationRequest
    )
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
)

import uvicorn
import requests

logging.basicConfig(level=os.getenv('LOG', 'WARNING'))
logger = logging.getLogger(__file__)

app = FastAPI()

channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

configuration = Configuration(
    access_token=channel_access_token
)

async_api_client = AsyncApiClient(configuration)
line_bot_api = AsyncMessagingApi(async_api_client)
parser = WebhookParser(channel_secret)


import google.generativeai as genai
from firebase import firebase
from utils import check_image_quake, check_location_in_message, get_current_weather, get_weather_data, simplify_data


firebase_url = os.getenv('FIREBASE_URL')
gemini_key = os.getenv('GEMINI_API_KEY')

# Initialize the Gemini Pro API
genai.configure(api_key=gemini_key)


@app.get("/health")
async def health():
    return 'ok'


@app.post("/webhooks/line")
async def handle_callback(request: Request):
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = await request.body()
    body = body.decode()

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    story_part = "這是一個關於勇者的故事。一天，勇者來到了一個岔路口，左邊是通往寶藏的道路，但充滿了危險；右邊是通往村莊的道路，能夠安全回家。你會怎麼選擇？"

    for event in events:
        logging.info(event)
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue
        text = event.message.text
        user_id = event.source.user_id

        msg_type = event.message.type
        fdb = firebase.FirebaseApplication(firebase_url, None)
        if event.source.type == 'group':
            user_chat_path = f'chat/{event.source.group_id}'
        else:
            user_chat_path = f'chat/{user_id}'
            chat_state_path = f'state/{user_id}'
        chatgpt = fdb.get(user_chat_path, None)

        if msg_type == 'text':

            if chatgpt is None:
                messages = []
            else:
                messages = chatgpt

            print('='*10)
            print(text)

            model = genai.GenerativeModel('gemini-1.5-pro')

            if text=="選單":
                reply_msg = TextSendMessage( 
                            text="Hello. How can I help you?",
                            quick_reply= QuickReply(
                                items=[
                                    QuickReplyButton(
                                        action=URIAction(label="情緒日記",uri="https://liff.line.me/2005781692-mkwZ19g6") ),
                                    QuickReplyButton(
                                        action=MessageAction(label="每日精選",text="每日精選") ),
                                    ]
                            )
                        )
                simple_msg = TextSendMessage(text="Hello, this is a test message")
                line_bot_api.push_message(user_id,[simple_msg])  
            elif text=="每日精選":
                response = model.generate_content(
                    f"請幫我推薦一本書就好，只要書名以及介紹文字（文字即可）"
                )
                reply_msg = response.text
            elif text=="故事分享":
                reply_msg = story_part
            else:
                
                response = model.generate_content(
                    f"以下是用戶的回覆：'{text}'。請判斷這是正面還是負面的回覆。只需回答 positive 或 negative."
                )
                print('='*10)
                sentiment = re.sub(r'[^A-Za-z]', '', response.text)
                sentiment = sentiment.lower()
                print(sentiment)
                if sentiment == "positive":
                    response = model.generate_content(
                        f"以下是用戶的回覆：'{text}'。"
                    )
                    reply_msg = response.text
                elif sentiment == "negative":
                    response = model.generate_content(
                        f"以下是用戶的回覆：'{text}'。請將句中負面、有爭議的詞彙替換成較委婉的詞彙。"
                    )
                    reply_msg = response.text
                else:
                    reply_msg = "無法判斷你的回覆。"

                # model = genai.GenerativeModel('gemini-pro')
                # messages.append({'role': 'user', 'parts': [text]})
                # response = model.generate_content(messages)
                # messages.append({'role': 'model', 'parts': [text]})
                # # 更新firebase中的對話紀錄
                # fdb.put_async(user_chat_path, None, messages)
                # reply_msg = response.text

            # line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=event.source.user_id, loadingSeconds=5))

            await line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages= TextMessage(text=reply_msg)
                    ))    
            return 'OK'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', default=8080))
    debug = True if os.environ.get(
        'API_ENV', default='develop') == 'develop' else False
    logging.info('Application will start...')
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=debug)
