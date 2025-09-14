# -*- coding: utf-8 -*-
import os
import time
import json
import asyncio
import pandas as pd
import pandas_ta as ta
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from binance.client import Client

# --- 從環境變數讀取金鑰 ---
API_KEY = os.environ.get('BINANCE_API_KEY')
API_SECRET = os.environ.get('BINANCE_API_SECRET')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# --- 全域變數 ---
client = Client(API_KEY, API_SECRET)
user_data = {}
monitoring_task = None
DATA_FILE = 'user_data.json'

# --- 數據持久化 ---
def load_user_data():
    global user_data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            user_data = json.load(f)
    else:
        user_data = {
            CHAT_ID: {
                "coins": [],
                "active": True,
                "interval": "15m",
                "rsi_period": 14,
                "rsi_overbought": 70,
                "rsi_oversold": 30
            }
        }
        save_user_data()

def save_user_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(user_data, f, indent=4)

# --- 主選單 ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text=None):
    keyboard = [
        [InlineKeyboardButton("➕ 新增幣種", callback_data='add_coin')],
        [InlineKeyboardButton("➖ 移除幣種", callback_data='remove_coin_menu')],
        [InlineKeyboardButton("📃 我的列表", callback_data='list_coins')],
        [InlineKeyboardButton("⚙️ 參數設定", callback_data='settings_menu')],
        [InlineKeyboardButton("🔔 暫停/恢復通知", callback_data='toggle_monitoring')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    is_active = user_data.get(CHAT_ID, {}).get('active', False)
    status_text = "🟢 (運行中)" if is_active else "🔴 (已暫停)"

    text = message_text or f"歡迎使用 RSI 監控 Bot {status_text}\n請選擇您要操作的項目："

    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup)

# --- 指令處理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context, f"✅ RSI 監控 Bot 已啟動\n\n您的專屬 Chat ID 是: `{update.effective_chat.id}`\n請用此 ID 設定您的環境變數。")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)

# --- 按鈕回調處理 ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'main_menu':
        await show_main_menu(update, context)
    elif data == 'add_coin':
        await query.edit_message_text(text="請輸入您想新增的幣種 (例如: BTCUSDT)")
        context.user_data['next_step'] = 'add_coin'
    elif data == 'list_coins':
        coins = user_data.get(CHAT_ID, {}).get('coins', [])
        if not coins:
            text = "您的監控列表是空的。"
        else:
            text = "您正在監控的幣種：\n- " + "\n- ".join(coins)
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主選單", callback_data='main_menu')]]))
    elif data == 'toggle_monitoring':
        user_data[CHAT_ID]['active'] = not user_data[CHAT_ID].get('active', True)
        save_user_data()
        await show_main_menu(update, context, f"通知狀態已更新。")
    elif data == 'remove_coin_menu':
        coins = user_data.get(CHAT_ID, {}).get('coins', [])
        if not coins:
            await query.edit_message_text("您的列表是空的，沒有可移除的幣種。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主選單", callback_data='main_menu')]]))
            return

        keyboard = [[InlineKeyboardButton(f"❌ {coin}", callback_data=f"remove_{coin}")] for coin in coins]
        keyboard.append([InlineKeyboardButton("返回主選單", callback_data='main_menu')])
        await query.edit_message_text("請點擊您想移除的幣種：", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith('remove_'):
        coin_to_remove = data.split('_')[1]
        if coin_to_remove in user_data[CHAT_ID]['coins']:
            user_data[CHAT_ID]['coins'].remove(coin_to_remove)
            save_user_data()
            await query.edit_message_text(f"`{coin_to_remove}` 已被移除。", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主-選單", callback_data='main_menu')]]))
        else:
            await query.edit_message_text(f"`{coin_to_remove}` 不在您的列表中。", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主選單", callback_data='main_menu')]]))

# --- 增加參數設定的處理 ---
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    params = user_data.get(CHAT_ID, {})
    text = f"⚙️ 目前參數設定:\n- K線週期 (Interval): `{params.get('interval', '15m')}`\n- RSI 週期 (Period): `{params.get('rsi_period', 14)}`\n- RSI 超買 (Overbought): `{params.get('rsi_overbought', 70)}`\n- RSI 超賣 (Oversold): `{params.get('rsi_oversold', 30)}`"

    keyboard = [
        [InlineKeyboardButton("修改 K 線週期", callback_data='set_interval')],
        [InlineKeyboardButton("修改 RSI 參數", callback_data='set_rsi')],
        [InlineKeyboardButton("返回主選單", callback_data='main_menu')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'settings_menu':
        await settings_menu(update, context)
    elif data == 'set_interval':
        await query.edit_message_text(text="請輸入新的 K 線週期 (例如: 5m, 15m, 1h, 4h, 1d):")
        context.user_data['next_step'] = 'set_interval'
    elif data == 'set_rsi':
        await query.edit_message_text(text="請輸入新的 RSI 參數，用逗號分隔 (週期,超買,超賣)，例如: 14,75,25")
        context.user_data['next_step'] = 'set_rsi'
    else: # This is a fallback to the main button handler
         await button_callback_handler(update, context)

# --- 文字訊息處理 ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    next_step = context.user_data.get('next_step')

    if next_step == 'add_coin':
        coin = update.message.text.upper().strip()
        if coin and "USDT" in coin:
            if 'coins' not in user_data[CHAT_ID]: user_data[CHAT_ID]['coins'] = []
            if coin not in user_data[CHAT_ID]['coins']:
                user_data[CHAT_ID]['coins'].append(coin)
                save_user_data()
                await update.message.reply_text(f"`{coin}` 已成功新增！", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"`{coin}` 已經在您的列表中了。", parse_mode='Markdown')
        else:
            await update.message.reply_text("格式錯誤，請輸入有效的交易對 (例如 BTCUSDT)。")
        context.user_data['next_step'] = None
        await show_main_menu(update, context)

    elif next_step == 'set_interval':
        interval = update.message.text.lower().strip()
        # Basic validation
        if interval in ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w']:
            user_data[CHAT_ID]['interval'] = interval
            save_user_data()
            await update.message.reply_text(f"K 線週期已更新為 `{interval}`。", parse_mode='Markdown')
        else:
            await update.message.reply_text("格式錯誤，請輸入有效的週期。")
        context.user_data['next_step'] = None
        await show_main_menu(update, context)

    elif next_step == 'set_rsi':
        try:
            period, overbought, oversold = map(int, update.message.text.strip().split(','))
            user_data[CHAT_ID]['rsi_period'] = period
            user_data[CHAT_ID]['rsi_overbought'] = overbought
            user_data[CHAT_ID]['rsi_oversold'] = oversold
            save_user_data()
            await update.message.reply_text(f"RSI 參數已更新。", parse_mode='Markdown')
        except ValueError:
            await update.message.reply_text("格式錯誤，請用逗號分隔三個數字。")
        context.user_data['next_step'] = None
        await show_main_menu(update, context)

# --- RSI 監控背景任務 ---
async def rsi_monitoring_task(context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(15) # Wait a bit on start
    while True:
        if not user_data.get(CHAT_ID, {}).get('active', False):
            await asyncio.sleep(30)
            continue

        coins = user_data.get(CHAT_ID, {}).get('coins', [])
        params = user_data.get(CHAT_ID, {})
        interval = params.get('interval', '15m')
        rsi_period = params.get('rsi_period', 14)
        rsi_overbought = params.get('rsi_overbought', 70)
        rsi_oversold = params.get('rsi_oversold', 30)

        for coin in coins:
            try:
                klines = client.get_historical_klines(coin, interval, "2 days ago UTC") # More data for RSI
                if len(klines) < rsi_period: continue

                df = pd.DataFrame(klines, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'])
                df['close'] = pd.to_numeric(df['close'])

                df.ta.rsi(length=rsi_period, append=True)
                df.dropna(inplace=True)
                latest_rsi = df[f'RSI_{rsi_period}'].iloc[-1]

                last_status_key = f"{coin}_status"
                last_status = context.bot_data.get(last_status_key, 'normal')
                new_status = last_status

                message = ""
                if latest_rsi > rsi_overbought and last_status != 'overbought':
                    message = f"🔔 *RSI 超買提醒* 🔔\n\n幣別: `{coin}`\n*當前 RSI: {latest_rsi:.2f}* (>{rsi_overbought})"
                    new_status = 'overbought'
                elif latest_rsi < rsi_oversold and last_status != 'oversold':
                    message = f"💰 *RSI 超賣提醒* 💰\n\n幣別: `{coin}`\n*當前 RSI: {latest_rsi:.2f}* (<{rsi_oversold})"
                    new_status = 'oversold'
                elif rsi_oversold < latest_rsi < rsi_overbought and last_status != 'normal':
                    new_status = 'normal'

                if message:
                    await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')

                context.bot_data[last_status_key] = new_status

            except Exception as e:
                print(f"Error processing {coin}: {e}")

            await asyncio.sleep(5) 

        await asyncio.sleep(60)

async def post_init(application: Application):
    load_user_data()
    global monitoring_task
    if monitoring_task is None:
        loop = asyncio.get_event_loop()
        monitoring_task = loop.create_task(rsi_monitoring_task(application))
        print("RSI monitoring task started.")

# --- 主程式 ---
def main():
    if not all([API_KEY, API_SECRET, BOT_TOKEN, CHAT_ID]):
        print("錯誤：缺少必要的環境變數。請檢查...")
        return

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Add settings handlers
    application.add_handler(CallbackQueryHandler(settings_callback_handler, pattern='^set_'))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Bot has started successfully!")
    application.run_polling()

if __name__ == '__main__':
    main()
