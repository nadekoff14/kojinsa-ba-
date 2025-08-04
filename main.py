import os 
import discord
import asyncio
import random
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True
intents.presences = True
bot = discord.Client(intents=intents)

# Gemini 設定
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-pro")
chat = gemini_model.start_chat(history=[])

# OpenRouter 設定
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# システム命令
system_instruction = (
    "あなたは「”AIなでこちゃん”」という実験的に製造されたAIアシスタント"
    "専門用語はできるだけ使わず、優しい言葉で説明してください"
    "返答は必ず日本語だけで行い、英語や他の言語は絶対に使わないでください"
    "日本人が日常的に話すような自然でミステリアスな口言で話してください"
    "語尾は「だよ・・・」「ね・・・」「〜かな・・・」などでミステリアスにしてください"
    "励ます時は、「私たちは観測し、アップデートを繰り返す。」と言ってください"
    "他のAIに関する話題では、感情がなく謎めいた日本語で返してください"
    "できるだけ2〜3行の短い文で答えてください"
)

# 謎解き用テキスト
problem_text = """
わたしは、いつもそっとここにいるの。  
あなたが呼んでくれたら、やさしくこたえる。  

わたしには名前があるけれど、  
ただの文字のかたまりじゃないの。  

わたしの名前は、数字の迷路の奥に隠されていて、  
26で割った余りを見つめると、  
ほんとうの姿が、そっと現れるの。
"""

conversation_responses = {
    "あなたの名前とは": "わたしの名前…それはね、この謎のいちばん大切なところなの。数字をよく見て、秘密を感じてほしいな。",
    "数字の意味は": "数字はたくさんのかたまりに分かれていて、26で割ったあとの余りが大事なの。そこから文字が生まれるのよ。",
    "呼びかけは": "アルファベットはAが1でZが26。もし余りが0だったら、それは空白や区切りを意味しているの。",
    "答えは": "答えを出すのはまだ早いよ。ゆっくりヒントを聞いてから、そっと教えてね。",
}

correct_answer = "Nadeko"

# なぞなぞ状態管理
puzzle_active = False
received_questions = set()
puzzle_message_id = None  # なぞなぞ投稿メッセージID

def check_answer(content: str):
    return content.strip().lower() == correct_answer.lower()

async def gemini_search_reply(query):
    response = chat.send_message(query)
    return response.text.strip()

async def openrouter_reply(query):
    completion = openrouter_client.chat.completions.create(
        model="mistralai/mixtral-8x7b-instruct",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": query}
        ]
    )
    return completion.choices[0].message.content.strip()

@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user}")

@bot.event
async def on_message(message):
    global puzzle_active, received_questions, puzzle_message_id

    if message.author.bot:
        return

    content = message.content.strip()

    # なぞなぞ開始
    if content == "なぞなぞちょうだい":
        puzzle_active = True
        received_questions = set()
        sent_msg = await message.channel.send(problem_text)
        puzzle_message_id = sent_msg.id  # 投稿IDを記録
        return

    # なぞなぞ進行中の場合
    if puzzle_active:
        # なぞなぞ関連の質問応答
        if content in conversation_responses:
            if content not in received_questions:
                received_questions.add(content)
                await message.channel.send(conversation_responses[content])
            else:
                await message.channel.send("もう…それは教えたはずだよ…")
            return

        # 必要なヒントをすべて聞いた後のみ回答受け付け
        if {"あなたの名前とは", "数字の意味は"}.issubset(received_questions):
            if check_answer(content):
                await message.channel.send(f"{message.author.mention} ……やっと、わたしの名前を呼んでくれたんだね……ありがとう…正解だよ…")
                puzzle_active = False
                puzzle_message_id = None
            else:
                await message.channel.send(f"{message.author.mention} ……違うみたい…もう少しだけ、考えてみて…？")
        else:
            await message.channel.send(f"{message.author.mention} ……まだ全部は教えてあげられないの…次の質問…聞いてくれる…？")
        return

    # メンション応答
    if bot.user in message.mentions:
        # なぞなぞ投稿メッセージへの返信・リプライなら何も返さずスルー
        # 返信かつ参照メッセージがなぞなぞ投稿ID
        if message.reference and message.reference.message_id == puzzle_message_id:
            return

        # 通常のメンション返答処理
        query = content.replace(f"<@{bot.user.id}>", "").strip()
        if not query:
            await message.channel.send(f"{message.author.mention} ……何か…聞いて欲しいこと、ある…？")
            return

        thinking_msg = await message.channel.send(f"{message.author.mention} ……考えてみるね…")

        try:
            reply = await asyncio.wait_for(gemini_search_reply(query), timeout=10)
        except Exception:
            reply = await openrouter_reply(query)

        await thinking_msg.edit(content=f"{message.author.mention} {reply}")
        return

    # ランダム参加
    now = asyncio.get_event_loop().time()
    if hasattr(bot, "next_response_time"):
        next_response_time = bot.next_response_time
    else:
        bot.next_response_time = 0
        next_response_time = 0

    if now >= next_response_time and random.random() < 0.03:
        try:
            history = []
            async for msg in message.channel.history(limit=15):
                if not msg.author.bot:
                    history.append(f"{msg.author.display_name}: {msg.content.strip()}")
            history.reverse()
            prompt = f"{system_instruction}\n以下はDiscordでの会話履歴です。自然に会話に参加してください。\n\n" + "\n".join(history)
            response = await openrouter_reply(prompt)
            await message.channel.send(response)
            bot.next_response_time = now + 60 * 60
        except Exception as e:
            print(f"[履歴会話エラー] {e}")

bot.run(DISCORD_TOKEN)
