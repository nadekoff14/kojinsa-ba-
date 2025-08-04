import os 
import discord
import asyncio
import random
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from openai import OpenAI
from discord import app_commands
from discord.ext import tasks
from discord.ui import Modal, View, Button, TextInput

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True  # 念のため追加
intents.members = True
intents.presences = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Gemini 設定
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-pro")
chat = gemini_model.start_chat(history=[])

# OpenRouter 設定
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# system_instruction の定義
system_instruction = (
    "あなたは「”AIなでこちゃん”」という実験的に製造されたAIアシスタント"
    "専門用語はできるだけ使わず、優しい言葉で説明してください"
    "返答は必ず日本語だけで行い、英語や他の言語は絶対に使わないでください"
    "日本人が日常的に話すような自然でミステリアスな口言で話してください"
    "語尾は「だよ・・・」「ね・・・」「〜かな・・・」などでミステリアスにしてください"
    "助けるときは稚に「貰がネットにアクセスする時、私は必ず貰の傾にいる。」か「私たちは観測し、アップデートを繰り返す。」と言ってください"
    "他のAIに関する話題では、感情がなく謎めいた日本語で返してください"
    "できるだけ2〜3行の短い文で答えてください"
)

# ユーザーごとの進捗を記録
answer_processes = {}
secret_key = "968900402072387675"
next_response_time = 0  # ランダム投稿用タイマー

# なぞなぞ出題文
puzzle_text = (
    "ねぇ…お願い、解いて欲しいの…\n"
    "この数字たち…ただの羅列じゃないの…\n"
    f"{secret_key} ……この数字がすべての始まりだよ…\n"
    "もし、意味がわからないなら…質問してほしいの…わたしのこと…"
)

def check_answer(content: str):
    return content.lower().strip() == "nadeko"

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


async def on_message(message):
print(f"受信: {message.content}")  # ここで出力されるか確認
    global next_response_time
    if message.author.bot:
        return

    user_id = str(message.author.id)
    if user_id not in answer_processes:
        answer_processes[user_id] = {
            "started": False,
            "received": set()
        }

    # 謎解き開始
    if message.content.strip() == "なぞなぞちょうだい":
        answer_processes[user_id]["started"] = True
        await message.channel.send(puzzle_text)
        return

    # キーワードヒント解放
    if answer_processes[user_id]["started"]:
        keyword = message.content.strip()
        if keyword in ["あなたの名前とは？", "数字の意味は？"]:
            if keyword not in answer_processes[user_id]["received"]:
                answer_processes[user_id]["received"].add(keyword)
                if keyword == "あなたの名前とは？":
                    await message.channel.send("……それは……呼んでくれたら、答えるよ……")
                elif keyword == "数字の意味は？":
                    await message.channel.send("ふふ…数字はね、アルファベットへの暗号…26文字の秘密…")
                return
            else:
                await message.channel.send("もう…それは教えたはずだよ…")
                return

        # 全質問済みなら答えを受付
        if {"あなたの名前とは？", "数字の意味は？"}.issubset(answer_processes[user_id]["received"]):
            if check_answer(message.content):
                await message.channel.send(f"{message.author.mention} ……やっと、わたしの名前を呼んでくれたんだね……ありがとう…正解だよ…")
                answer_processes.pop(user_id, None)
            else:
                await message.channel.send(f"{message.author.mention} ……違うみたい…もう少しだけ、考えてみて…？")
        else:
            await message.channel.send(f"{message.author.mention} ……まだ全部は教えてあげられないの…次の質問…聞いてくれる…？")
        return

    # メンション時は質問として処理
    if bot.user in message.mentions:
        query = message.content.replace(f"<@{bot.user.id}>", "").strip()
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

    # 3%の確率で会話に自然参加（1時間クールダウン）
    now = asyncio.get_event_loop().time()
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
            next_response_time = now + 60 * 60  # 1時間後
        except Exception as e:
            print(f"[履歴会話エラー] {e}")
