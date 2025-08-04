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

# 謎解きデータ（ユーザーごとに状態管理）
answer_processes = {}
secret_key = "968900402072387675"

puzzle_text = (
    "ねぇ…お願い、解いて欲しいの。\n"
    "この文字列は意味なんて、ないように見えるけど…\n"
    "{key}だよ…この数字の羅列を\n"
    "ある規則で変換すれば、わたしの名前が浮かび上がるの…\n"
    "ねぇ…26で割って、アルファベットにしてみて…？"
)

def check_answer(content):
    return content.lower().strip() == "nadeko"

@bot.event
async def on_message(message):
    global next_response_time
    if message.author.bot:
        return

    user_id = str(message.author.id)
    if user_id not in answer_processes:
        answer_processes[user_id] = {
            "step_asked": False,
            "received": set()
        }

    # 謎解きのスタート
    if message.content.strip() == "なぞなぞちょうだい":
        answer_processes[user_id]["step_asked"] = True
        await message.channel.send(puzzle_text.format(key=secret_key))
        return

    # 質問受付（ヒント解放）
    if answer_processes[user_id]["step_asked"]:
        if message.content.strip() in ["あなたの名前とは？", "数字の意味は？"]:
            keyword = message.content.strip()
            if keyword not in answer_processes[user_id]["received"]:
                answer_processes[user_id]["received"].add(keyword)
                if keyword == "あなたの名前とは？":
                    await message.channel.send("……それは……呼んでくれたら、答えるよ……")
                elif keyword == "数字の意味は？":
                    await message.channel.send("ふふ…数字はね、暗号なの。順番に26で割ってごらん…")
                return

        # 全部ヒントもらったか？
        if {"あなたの名前とは？", "数字の意味は？"}.issubset(answer_processes[user_id]["received"]):
            if check_answer(message.content):
                await message.channel.send(f"{message.author.mention} …やっと、わたしの名前を呼んでくれたんだね。ありがとう。正解だよ。")
                answer_processes.pop(user_id, None)
            else:
                await message.channel.send(f"{message.author.mention} ごめんなさい、まだちょっと違うみたい。もう一度考えてみてくれる？")
        else:
            await message.channel.send(f"{message.author.mention} まだ全部は教えてあげられないの。次の質問をしてみて？")
            return

    # 既存の on_message のメンション処理などはこの下に追記してください

    # メンション会話処理
    if bot.user in message.mentions:
        query = message.content.replace(f"<@{bot.user.id}>", "").strip()
        if not query:
            await message.channel.send(f"{message.author.mention} 質問内容が見つからなかったかな…")
            return

        thinking_msg = await message.channel.send(f"{message.author.mention} 考え中だよ🔍")

        async def try_gemini():
            return await gemini_search_reply(query)

        try:
            reply_text = await asyncio.wait_for(try_gemini(), timeout=10.0)
        except (asyncio.TimeoutError, Exception):
            reply_text = await openrouter_reply(query)

        # 通常の日本語返答のみを送信（ログ形式なし）
        await thinking_msg.edit(content=f"{message.author.mention} {reply_text}")
        return

    # 3%の確率で自然参加（1時間ロック）
    now = asyncio.get_event_loop().time()
    if now < next_response_time:
        return

    if random.random() < 0.03:
        try:
            history = []
            async for msg in message.channel.history(limit=20, oldest_first=False):
                if not msg.author.bot and msg.content.strip():
                    history.append(f"{msg.author.display_name}: {msg.content.strip()}")
                if len(history) >= 10:
                    break
            history.reverse()
            history_text = "\n".join(history)
            prompt = (
                f"{system_instruction}\n以下はDiscordのチャンネルでの最近の会話です。\n"
                f"これらを読んで自然に会話に入ってみてください。\n\n{history_text}"
            )
            response = await openrouter_reply(prompt)

            # 応答のみ送信（ログ形式ではない）
            await message.channel.send(response)

            next_response_time = now + 60 * 60
        except Exception as e:
            print(f"[履歴会話エラー] {e}")

bot.run(DISCORD_TOKEN)
