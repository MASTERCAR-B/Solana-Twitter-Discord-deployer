#Mastercard god

import json
import time
import os
import logging
import requests
import asyncio
import threading
import subprocess
import webbrowser
import discord
import shutil
import tempfile
import urllib.request
from pathlib import Path
from discord.ext import commands
from discord.ui import Button, View
from google import genai
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
RELAY_MAPPINGS = {
    "": [""], #serenity
}

MEMECOIN_BUTTON_CHANNEL_ID = ""  # Example channel ID

USER_TOKEN = ""
RELAY_DELAY = 2
DATA_DIR = "relay_data"

BOT_TOKEN = ""
GEMINI_API_KEY = ""

chrome_path = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(chrome_path))

user_data_dir = os.path.join(os.environ['USERPROFILE'], 'AppData', 'Local', 'Google', 'Chrome', 'User Data')

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

webhook_to_original = {}
processed_embeds = {}

def ensure_data_directory():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def get_headers():
    return {
        "Authorization": USER_TOKEN,
        "Content-Type": "application/json"
    }

def get_last_message_id(channel_id):
    ensure_data_directory()
    file_path = os.path.join(DATA_DIR, f"{channel_id}_last_message.txt")
    
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return f.read().strip()
    return None

def save_last_message_id(channel_id, message_id):
    ensure_data_directory()
    file_path = os.path.join(DATA_DIR, f"{channel_id}_last_message.txt")
    
    with open(file_path, 'w') as f:
        f.write(message_id)

def get_new_messages(channel_id):
    last_message_id = get_last_message_id(channel_id)
    
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=50"
    
    response = requests.get(url, headers=get_headers())
    
    if response.status_code != 200:
        logging.error(f"Error fetching messages from channel {channel_id}: {response.status_code}")
        logging.error(response.text)
        return []
    
    messages = response.json()
    
    if last_message_id:
        new_messages = []
        for msg in messages:
            if msg["id"] > last_message_id:
                new_messages.append(msg)
        new_messages.sort(key=lambda x: x["id"])
        return new_messages
    
    if messages:
        save_last_message_id(channel_id, messages[0]["id"])
    
    return []

def get_channel_name(channel_id):
    url = f"https://discord.com/api/v9/channels/{channel_id}"
    
    response = requests.get(url, headers=get_headers())
    
    if response.status_code != 200:
        return f"Channel {channel_id}"
    
    channel_data = response.json()
    return channel_data.get("name", f"Channel {channel_id}")

def format_embed_for_webhook(embed):
    formatted_embed = {}
    
    for field in ["title", "description", "url", "timestamp", "color", "footer", 
                 "image", "thumbnail", "author", "fields"]:
        if field in embed:
            formatted_embed[field] = embed[field]
    
    return formatted_embed

def send_webhook_message(webhook_url, message, channel_name):
    content = message.get("content", "")
    author = message.get("author", {})
    username = author.get("username", "Unknown User")
    discriminator = author.get("discriminator", "0000")
    
    user_id = author.get("id", "")
    avatar_hash = author.get("avatar", "")
    avatar_url = ""
    
    if avatar_hash:
        avatar_format = "gif" if avatar_hash.startswith("a_") else "png"
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{avatar_format}?size=128"
    else:
        default_avatar_id = int(discriminator) % 5
        avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_avatar_id}.png"
    
    webhook_data = {
        "username": f"{username} (from {channel_name})",
        "avatar_url": avatar_url,
        "content": content
    }
    
    if "embeds" in message and message["embeds"]:
        webhook_data["embeds"] = [
            format_embed_for_webhook(embed) 
            for embed in message["embeds"] 
            if embed.get("type") == "rich"  
        ]
    
    response = requests.post(webhook_url, json=webhook_data)
    
    if response.status_code == 204:
        logging.info(f"Successfully relayed message from {username} to webhook")
    else:
        logging.error(f"Error sending webhook: {response.status_code}")
        logging.error(response.text)

def monitor_channel(channel_id, webhook_urls):
    channel_name = get_channel_name(channel_id)
    logging.info(f"Starting monitoring for channel: {channel_name} ({channel_id})")
    
    while True:
        try:
            new_messages = get_new_messages(channel_id)
            
            for message in new_messages:
                for webhook_url in webhook_urls:
                    send_webhook_message(webhook_url, message, channel_name)
                
                save_last_message_id(channel_id, message["id"])
            
            time.sleep(RELAY_DELAY)
            
        except Exception as e:
            logging.error(f"Error occurred while monitoring channel {channel_id}: {str(e)}")
            time.sleep(5) 

async def generate_memecoin(embed_content):
    try:
        prompt = f
        """
        Based on this Discord embed content: "{embed_content}", create a meme cryptocurrency with the following:
        1. A catchy ticker symbol (3-5 characters)
        2. A creative name that relates to the content
        3. A brief, humorous description (max 50 words)
        
        Format your response as JSON only with no explanation:
        {{
            "ticker": "TICKER",
            "name": "Name of Coin",
            "description": "Brief description"
        }}"""
        
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )        
        try:
            result = json.loads(response.text)
            return result
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract the JSON portion
            text = response.text
            start_idx = text.find('{')
            end_idx = text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_text = text[start_idx:end_idx]
                return json.loads(json_text)
            else:
                raise Exception("Could not parse Gemini response as JSON")
    
    except Exception as e:
        logging.error(f"Error generating memecoin: {str(e)}")
        return {
            "ticker": "ERROR",
            "name": "Generation Failed",
            "description": f"Could not generate memecoin: {str(e)}"
        }

async def extract_embed_content(embed):
    content = ""
    
    if embed.title:
        content += embed.title + " "
    
    if embed.description:
        content += embed.description + " "
    
    if embed.fields:
        for field in embed.fields:
            content += field.name + " " + field.value + " "
    
    if embed.footer:
        content += embed.footer.text + " "
    
    return content.strip()

def get_embed_image_url(embed):
    if embed.image and embed.image.url:
        return embed.image.url
        
    if embed.thumbnail and embed.thumbnail.url:
        return embed.thumbnail.url
        
    return None

def kill_chrome():
    try:
        subprocess.run(['taskkill', '/f', '/im', 'chrome.exe'], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

async def create_token_on_pump(ctx, name, ticker, description, image_url=None):
    await ctx.send(f"Creating token with name: {name}, ticker: {ticker}, description: {description}")
    
    await ctx.send("Closing any running Chrome instances for clean automation...")
    success = kill_chrome()
    if success:
        await ctx.send("Chrome closed successfully.")
    else:
        await ctx.send("Could not close Chrome. Please close Chrome manually, then try again.")
        return
       
    try:
        chrome_options = Options()
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        chrome_options.add_argument("--profile-directory=Default")  # Usually the default profile
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_experimental_option("detach", True)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        driver = webdriver.Chrome(options=chrome_options)
        await ctx.send("Chrome launched with your profile - Phantom should be available.")
        
        driver.get('https://pump.fun/create')
        await ctx.send("Opening pump.fun/create - waiting for page to load...")
        time.sleep(1)  # Reduced time to 1s as requested
        
        connect_buttons = driver.find_elements(By.XPATH, 
            "//button[contains(text(), 'Connect') or contains(text(), 'Wallet')]")
        
        if connect_buttons:
            await ctx.send("Found wallet connect button - clicking it...")
            connect_buttons[0].click()
            time.sleep(1)  # Reduced wait time
            
            # Look for Phantom option
            phantom_options = driver.find_elements(By.XPATH, 
                "//*[contains(text(), 'Phantom') or contains(@alt, 'Phantom')]")
            
            if phantom_options:
                await ctx.send("Found Phantom option - clicking it...")
                for element in phantom_options:
                    try:
                        element.click()
                        await ctx.send("Clicked on Phantom option.")
                        break
                    except:
                        continue
                
                await ctx.send("Waiting for Phantom authorization popup...")
                time.sleep(3)  # Reduced wait time from 10s to 3s
                await ctx.send("Please approve any Phantom popups if they appear.")
            else:
                await ctx.send("Could not find Phantom wallet option. You may need to connect manually.")
        
        current_url = driver.current_url
        if "create" not in current_url.lower():
            await ctx.send(f"Not on creation page. Navigating to pump.fun/create...")
            driver.get('https://pump.fun/create')
            time.sleep(3)
        
        await ctx.send("Looking for form fields...")
        
        all_inputs = driver.find_elements(By.TAG_NAME, "input")
        all_textareas = driver.find_elements(By.TAG_NAME, "textarea")
        
        await ctx.send(f"Found {len(all_inputs)} input fields and {len(all_textareas)} textarea fields.")

        
        await ctx.send("Attempting to fill form using JavaScript...")
        fill_result = driver.execute_script(
          """
            // Try to find inputs by placeholder text
            let nameInput = document.querySelector('input[placeholder="name your coin"]');
            if (!nameInput) {
                // Try broader match
                const inputs = document.querySelectorAll('input');
                for (const input of inputs) {
                    if (input.placeholder && (
                        input.placeholder.toLowerCase().includes('name') || 
                        input.placeholder.toLowerCase().includes('coin')
                    )) {
                        nameInput = input;
                        break;
                    }
                }
            }
            
            let tickerInput = document.querySelector('input[placeholder="add a coin ticker (e.g. DOGE)"]');
            if (!tickerInput) {
                // Try broader match
                const inputs = document.querySelectorAll('input');
                for (const input of inputs) {
                    if (input.placeholder && (
                        input.placeholder.toLowerCase().includes('ticker') || 
                        input.placeholder.toLowerCase().includes('doge')
                    )) {
                        tickerInput = input;
                        break;
                    }
                }
            }
            
            let descInput = document.querySelector('textarea[placeholder="write a short description"]');
            if (!descInput) {
                // Try any textarea
                const textareas = document.querySelectorAll('textarea');
                if (textareas.length > 0) {
                    descInput = textareas[0];
                }
            }
            
            // Fill fields if found
            if (nameInput) {
                nameInput.value = arguments[0];
                nameInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
            
            if (tickerInput) {
                tickerInput.value = arguments[1];
                tickerInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
            
            if (descInput) {
                descInput.value = arguments[2];
                descInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
            
            return {
                nameFound: !!nameInput,
                tickerFound: !!tickerInput, 
                descFound: !!descInput
            };
        """, name, ticker, description)
        
        await ctx.send(f"JavaScript fill results: {fill_result}")
        
        await ctx.send("Attempting to fill form using Selenium...")
        
        name_filled = False
        try:
            name_fields = driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'name') or contains(@placeholder, 'coin')]")
            if name_fields:
                name_fields[0].clear()
                name_fields[0].send_keys(name)
                name_filled = True
                await ctx.send("Name field filled using Selenium.")
            else:
                first_input = driver.find_elements(By.TAG_NAME, "input")
                if first_input and len(first_input) > 0:
                    first_input[0].clear()
                    first_input[0].send_keys(name)
                    name_filled = True
                    await ctx.send("Filled first input field with name (fallback).")
        except Exception as e:
            await ctx.send(f"Error filling name field: {str(e)}")
        
        ticker_filled = False
        try:
            ticker_fields = driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'ticker') or contains(@placeholder, 'DOGE')]")
            if ticker_fields:
                ticker_fields[0].clear()
                ticker_fields[0].send_keys(ticker)
                ticker_filled = True
                await ctx.send("Ticker field filled using Selenium.")
            elif not name_filled and len(all_inputs) >= 2:
                # Try second input as last resort
                all_inputs[1].clear()
                all_inputs[1].send_keys(ticker)
                ticker_filled = True
                await ctx.send("Filled second input field with ticker (fallback).")
        except Exception as e:
            await ctx.send(f"Error filling ticker field: {str(e)}")
        
        desc_filled = False
        try:
            desc_fields = driver.find_elements(By.XPATH, "//textarea[contains(@placeholder, 'description') or contains(@placeholder, 'short')]")
            if desc_fields:
                desc_fields[0].clear()
                desc_fields[0].send_keys(description)
                desc_filled = True
                await ctx.send("Description field filled using Selenium.")
            elif all_textareas:
                # Try any textarea as last resort
                all_textareas[0].clear()
                all_textareas[0].send_keys(description)
                desc_filled = True
                await ctx.send("Filled textarea with description (fallback).")
        except Exception as e:
            await ctx.send(f"Error filling description field: {str(e)}")
        
        if image_url:
            try:
                await ctx.send("Downloading image from Discord...")
                
                temp_dir = Path(tempfile.gettempdir()) / "discord_images"
                temp_dir.mkdir(exist_ok=True)
                
                image_filename = f"memecoin_image_{int(time.time())}.png"
                image_path = temp_dir / image_filename
                
                urllib.request.urlretrieve(image_url, image_path)
                
                await ctx.send(f"Image downloaded to {image_path}")
                
                file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                
                if file_inputs:
                    await ctx.send("Found image upload field, attempting to upload...")
                    # Send the file path to the input element
                    file_inputs[0].send_keys(str(image_path.absolute()))
                    await ctx.send("Image uploaded successfully!")
                else:
                    upload_elements = driver.find_elements(By.XPATH, 
                        "//*[contains(text(), 'Upload') or contains(text(), 'Image') or contains(text(), 'Logo')]")
                    
                    if upload_elements:
                        await ctx.send("Found potential upload element, clicking it...")
                        upload_elements[0].click()
                        time.sleep(1)
                        
                        file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                        if file_inputs:
                            file_inputs[0].send_keys(str(image_path.absolute()))
                            await ctx.send("Image uploaded after clicking upload button!")
                        else:
                            await ctx.send("Couldn't find file input after clicking. Manual upload may be needed.")
                    else:
                        await ctx.send("Could not find image upload field. You may need to upload manually.")
                        await ctx.send(f"Local image saved at: {image_path}")
            except Exception as e:
                await ctx.send(f"Error downloading/uploading image: {str(e)}")
                await ctx.send(f"Please manually save and upload the image: {image_url}")
        
        create_buttons = driver.find_elements(By.XPATH, 
            "//button[contains(text(), 'Create') or contains(text(), 'Submit') or contains(text(), 'Launch') or contains(text(), 'Mint')]")
        
        if create_buttons:
            await ctx.send(f"Found {len(create_buttons)} potential submit button(s). You can click it when ready.")
        else:
            await ctx.send("Could not find a submit button. You may need to submit manually.")
        
        await ctx.send("Form filling complete! Browser will remain open so you can review and submit.")
        await ctx.send(f"If any fields were not filled correctly, here are the values to enter manually:\nName: {name}\nTicker: {ticker}\nDescription: {description}")
        
    except Exception as e:
        await ctx.send(f"Error during automation: {str(e)}")
        await ctx.send("Opening pump.fun manually as fallback...")
        webbrowser.get('chrome').open('https://pump.fun/create')
        await ctx.send(f"Please manually fill out the form with:\nName: {name}\nTicker: {ticker}\nDescription: {description}")

class MemeCoinButton(Button):
    def __init__(self, embed_content, image_url=None):
        super().__init__(style=discord.ButtonStyle.primary, label="Generate & Create Meme Coin", custom_id=f"memecoin_{int(time.time())}")
        self.embed_content = embed_content
        self.image_url = image_url
    
    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=False, thinking=True)
        
        memecoin = await generate_memecoin(self.embed_content)
        
        response_embed = discord.Embed(
            title=f"🚀 {memecoin['name']} ({memecoin['ticker']})",
            description=memecoin['description'],
            color=0xfaa61a
        )
        
        if self.image_url:
            response_embed.set_image(url=self.image_url)
            
        response_embed.set_footer(text=f"Generated based on embed content • {interaction.user.name}")
        
        await interaction.followup.send(embed=response_embed)
        
        await create_token_on_pump(
            interaction.followup, 
            memecoin['name'], 
            memecoin['ticker'], 
            memecoin['description'],
            self.image_url
        )
        
        self.disabled = True
        self.label = "Meme Coin Generated & Created"
        await interaction.message.edit(view=self.view)

@bot.event
async def on_ready():
    logging.info(f"Bot is ready and logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.error(f"Failed to sync commands: {e}")

@bot.event
async def on_message(message):
    if str(message.channel.id) == MEMECOIN_BUTTON_CHANNEL_ID:
        if message.webhook_id or message.author.bot:
            if message.embeds:
                for embed in message.embeds:
                    embed_id = f"{message.channel.id}_{message.id}_{embed.title}"
                    
                    if embed_id not in processed_embeds:
                        processed_embeds[embed_id] = True
                        
                        embed_content = await extract_embed_content(embed)
                        
                        image_url = get_embed_image_url(embed)
                        
                        view = View(timeout=None)
                        view.add_item(MemeCoinButton(embed_content, image_url))
                        
                        try:
                            await message.reply(view=view)
                            logging.info(f"Added meme coin button to embed in channel {message.channel.id}: {embed.title}")
                        except Exception as e:
                            logging.error(f"Failed to add button: {e}")
    
    await bot.process_commands(message)

@bot.command(name='createtoken')
async def create_token(ctx, name: str, ticker: str, description: str):
    await create_token_on_pump(ctx, name, ticker, description)

def relay_messages():
    logging.info("Starting Enhanced Discord multi-channel message relayer...")
    
    threads = []
    for channel_id, webhook_urls in RELAY_MAPPINGS.items():
        thread = threading.Thread(
            target=monitor_channel,
            args=(channel_id, webhook_urls),
            daemon=True
        )
        threads.append(thread)
        thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down relayer...")

async def start_bot():
    try:
        await bot.start(BOT_TOKEN)
    except Exception as e:
        logging.error(f"Error starting bot: {e}")

if __name__ == "__main__":
    relay_thread = threading.Thread(target=relay_messages, daemon=True)
    relay_thread.start()
    
    asyncio.run(start_bot())
