import logging
import os
import re
import sys
if os.getenv('API_ENV') != 'production':
    from dotenv import load_dotenv

    load_dotenv()


from fastapi import FastAPI, HTTPException, Request
from datetime import datetime
from linebot.v3.webhook import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
    URIAction)
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
    
    story_start = "當蘇珊與阿俊第一次相遇時，他們都覺得彼此是命中注定的另一半。蘇珊是一位善解人意、體貼的女子，而阿俊則是個幽默風趣、充滿自信的男人。他們的感情一開始非常甜蜜，彼此之間充滿了無盡的愛意。隨著時間的推移，蘇珊發現自己在這段關係中越來越多地付出。她每天為阿俊準備早餐，幫他整理房間，甚至在他忙於工作時為他跑腿辦事。阿俊起初對蘇珊的關愛表示感激，常常讚美她的體貼和周到。然而，隨著日子一天天過去，阿俊漸漸習慣了蘇珊的付出，並開始將這些努力視為理所當然。有一天，蘇珊下班後拖著疲憊的身軀回到家，發現阿俊正舒適地躺在沙發上看電視。蘇珊輕聲問道：「阿俊，今天晚餐你想吃什麼？」阿俊頭也不回地回答：「隨便，妳做什麼都行。」這句話深深刺痛了蘇珊的心，她感到自己的努力與付出被完全忽視。"
    story_end = "蘇珊深吸一口氣，忍住即將落下的淚水，說道：「我當然願意照顧你，但這不是單方面的。我需要你的支持和關心，這樣我們的關係才能更加健康和諧。」阿俊終於意識到蘇珊的困擾。他回憶起過去那些被他忽略的細節，發現自己確實在無意中忽視了蘇珊的感受和付出。他誠懇地道歉，並承諾會改變，更多地參與到兩人的生活中，共同分擔責任。從那天起，阿俊開始主動分擔家務，關心蘇珊的需求，並經常給她帶來小小的驚喜。他們的關係也因此變得更加親密和堅定。蘇珊感受到阿俊的改變，心中那份失落感逐漸被幸福取代。這個故事告訴我們，在兩性交往中，雙方的付出和關心是維繫關係的重要基石。只有在彼此互相支持和理解的基礎上，愛情才能夠長久地走下去。"
    f = open("mood.txt",'r')
    for event in events:
        logging.info(event)
        print(event)
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

            bot_condition = {
                "功能選單": 'A',
                "每日推薦書籍": 'B',
                "故事分享": 'C',
                "故事後續":'D',
                "非暴力溝通": 'E',
                "聊天": 'F'
            }

            model = genai.GenerativeModel('gemini-1.5-pro')
            response = model.generate_content(
                f'請判斷 {text} 裡面的文字屬於 {bot_condition} 裡面的哪一項？符合條件請回傳對應的英文文字就好，不要有其他的文字與字元。如果只輸入情緒兩個字，請忽略這則訊息')
            print('='*10)
            text_condition = re.sub(r'[^A-Za-z]', '', response.text)
            print(text_condition)
            print('='*10)
            if text == "功能選單":
                reply_msg = TextMessage(
                            text="我能怎麼幫您呢？",
                            quick_reply=QuickReply(items=[
                                QuickReplyItem(
                                        action=URIAction(label="情緒日記",uri="https://liff.line.me/2005781692-mkwZ19g6") ),
                                QuickReplyItem(
                                        action=URIAction(label="認識情緒",uri="https://liff.line.me/2005781692-JVRmrwoZ") ),
                                QuickReplyItem(
                                    action=MessageAction(label="每日精選書籍",text="每日推薦書籍")),
                                QuickReplyItem(
                                    action=MessageAction(label="故事分享",text="故事分享")),
                                QuickReplyItem(
                                    action=MessageAction(label="非暴力溝通",text="非暴力溝通")),
                                ]
                            ),
                        )

            elif text_condition == 'B':
                mood = f.read()
                response = model.generate_content(
                    f'請幫我推薦一本書就好，符合我今天的心情：{mood}，只要書名以及介紹文字，請不要回傳特殊符號')
                reply_msg = TextMessage(text=response.text)
            elif text_condition == 'C':
                reply_msg = story_start+"\n如果你是蘇珊你會怎麼做呢？"
                reply_msg = TextMessage(text=reply_msg)
            elif text_condition == 'D':    
                reply_msg = story_end
                reply_msg = TextMessage(text=reply_msg)
            elif text_condition == 'E':
                reply_msg = "非暴力溝通\n1. 發生什麼事了？跟我分享可以嗎？\n2. 跟我說說你的感受\n3. 提出請求，怎麼樣能夠真正幫助你呢？"
                reply_msg = TextMessage(text=reply_msg)
            elif text_condition == 'F':
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
                    reply_msg = TextMessage(text=response.text)
                elif sentiment == "negative":
                    response = model.generate_content(
                        f"以下是用戶的回覆：'{text}'。請將句中負面、有爭議的詞彙替換成較委婉的詞彙。"
                    )
                    reply_msg = TextMessage(text=response.text)
                else:
                    reply_msg = TextMessage(text="無法判斷你的回覆。")
            else:
                # model = genai.GenerativeModel('gemini-pro')
                messages.append({'role': 'user', 'parts': [text]})
                response = model.generate_content(messages)
                messages.append({'role': 'model', 'parts': [text]})
                # 更新firebase中的對話紀錄
                fdb.put_async(user_chat_path, None, messages)
                reply_msg = TextMessage(text=response.text)

            await line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply_msg]
                ))
    f.close()
    return 'OK'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', default=8080))
    debug = True if os.environ.get(
        'API_ENV', default='develop') == 'develop' else False
    logging.info('Application will start...')
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=debug)
