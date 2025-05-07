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
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
RELAY_MAPPINGS = {
    "": [""], #serenity
}

# NEW: Specify the channel where meme coin buttons should be added
# Replace this with the specific channel ID you want to enable the button for
MEMECOIN_BUTTON_CHANNEL_ID = ""  # Example channel ID

USER_TOKEN = ""
RELAY_DELAY = 2
DATA_DIR = "relay_data"

# Bot configuration
BOT_TOKEN = ""
GEMINI_API_KEY = ""

# Chrome user profile path with Phantom extension
user_data_dir = os.path.join(os.environ['USERPROFILE'], 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default')

# Configure Google Gemini AI
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Initialize Discord client for the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Dictionary to track webhook message IDs to original messages
webhook_to_original = {}
processed_embeds = {}

# Create directories
def ensure_data_directory():
    """Create the data directory if it doesn't exist."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def get_headers():
    """Return headers with user authorization token for Discord API requests."""
    return {
        "Authorization": USER_TOKEN,
        "Content-Type": "application/json"
    }

def get_last_message_id(channel_id):
    """Retrieve the last processed message ID from file for a specific channel."""
    ensure_data_directory()
    file_path = os.path.join(DATA_DIR, f"{channel_id}_last_message.txt")
    
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return f.read().strip()
    return None

def save_last_message_id(channel_id, message_id):
    """Save the last processed message ID to file for a specific channel."""
    ensure_data_directory()
    file_path = os.path.join(DATA_DIR, f"{channel_id}_last_message.txt")
    
    with open(file_path, 'w') as f:
        f.write(message_id)

def get_new_messages(channel_id):
    """Fetch new messages from a specific source channel.
    On first run, records the latest message ID but doesn't return any messages
    to prevent initial spam."""
    last_message_id = get_last_message_id(channel_id)
    
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=50"
    
    response = requests.get(url, headers=get_headers())
    
    if response.status_code != 200:
        logging.error(f"Error fetching messages from channel {channel_id}: {response.status_code}")
        logging.error(response.text)
        return []
    
    messages = response.json()
    
    # If no messages were found
    if not messages:
        return []
    
    # On first run (no last_message_id), save the most recent message ID
    # Discord returns messages in descending order (newest first)
    # So messages[0] is the most recent message
    if not last_message_id:
        if messages:
            # Save the most recent message ID to start from
            save_last_message_id(channel_id, messages[0]["id"])
        # Don't return any messages on first run to prevent spam
        return []
    
    # For subsequent runs, return only messages newer than last_message_id
    new_messages = []
    for msg in messages:
        if msg["id"] > last_message_id:
            new_messages.append(msg)
    
    # Sort by ID to ensure chronological order (oldest first)
    new_messages.sort(key=lambda x: x["id"])
    
    # If we found new messages, update the last_message_id
    if new_messages:
        save_last_message_id(channel_id, new_messages[-1]["id"])
    
    return new_messages
def get_channel_name(channel_id):
    """Get the name of a channel from its ID."""
    url = f"https://discord.com/api/v9/channels/{channel_id}"
    
    response = requests.get(url, headers=get_headers())
    
    if response.status_code != 200:
        return f"Channel {channel_id}"
    
    channel_data = response.json()
    return channel_data.get("name", f"Channel {channel_id}")

def format_embed_for_webhook(embed):
    """Format Discord embed for webhook compatibility."""
    formatted_embed = {}
    
    for field in ["title", "description", "url", "timestamp", "color", "footer", 
                 "image", "thumbnail", "author", "fields"]:
        if field in embed:
            formatted_embed[field] = embed[field]
    
    return formatted_embed

def send_webhook_message(webhook_url, message, channel_name):
    """Send message to a webhook with enhanced formatting and track message ID."""
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
    """Monitor a specific channel and relay messages to all associated webhooks."""
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
    """Generate memecoin details using Gemini AI based on the embed content"""
    try:
        prompt = f"""Based on this Discord embed content: "{embed_content}", create a meme cryptocurrency with the following:
        1. A catchy ticker symbol (3-5 characters)
        2. A creative name that relates to the content
        3. A brief, humorous description (max 50 words)
        
        Format your response as JSON only with no explanation:
        {{
            "ticker": "TICKER",
            "name": "Name of Coin",
            "description": "Brief description"
        }} """

        
        # Call Gemini API
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )        
        # Parse the response
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
    """Extract relevant content from a Discord embed"""
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
    """Extract image URL from a Discord embed if present"""
    # Check for image property first
    if embed.image and embed.image.url:
        return embed.image.url
        
    # Check for thumbnail if no main image
    if embed.thumbnail and embed.thumbnail.url:
        return embed.thumbnail.url
        
    return None

def kill_chrome():
    """Kill all Chrome processes"""
    try:
        subprocess.run(['taskkill', '/f', '/im', 'chrome.exe'], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

async def create_token_on_pump(ctx, name, ticker, description, image_url=None):
    """Open pump.fun and create a token with the given details using undetected_chromedriver"""
    await ctx.send(f"Creating token with name: {name}, ticker: {ticker}, description: {description}")
    
    try:
        # Setup undetected_chromedriver options for better performance
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={user_data_dir}")
        
        driver = uc.Chrome(options=options)
        
        driver.get('https://pump.fun/create')
        
        # Wait explicitly for page to load
        await ctx.send("Waiting for page to load...")
        
        time.sleep(3)
        await ctx.send("Page loaded - checking for wallet connection...")
        
        # More robust form field detection using JavaScript
        script = """
        function findInputByPlaceholder(placeholderText) {
            const inputs = document.querySelectorAll('input, textarea');
            for (let input of inputs) {
                if (input.placeholder && input.placeholder.toLowerCase().includes(placeholderText.toLowerCase())) {
                    return input;
                }
            }
            return null;
        }
        
        const fields = {
            name: findInputByPlaceholder('name'),
            ticker: findInputByPlaceholder('ticker'),
            description: document.querySelector('textarea')
        };
        
        return fields;
        """
        
        form_fields = driver.execute_script(script)
        
        # Fill name field
        try:
            name_field = None
            # Try JavaScript approach first
            if driver.execute_script("return arguments[0] !== null", form_fields['name']):
                name_field = form_fields['name']
                driver.execute_script("arguments[0].value = arguments[1]", name_field, name)
                await ctx.send("Name field filled via JavaScript.")
            else:
                # Try different approaches to find the name field
                selectors = [
                    "//input[@placeholder='name your coin']",
                    "//input[contains(@placeholder, 'name')]",
                    "//input[contains(@id, 'name')]",
                    "//input[contains(@class, 'name')]"
                ]
                
                for selector in selectors:
                    try:
                        name_field = WebDriverWait(driver, 2).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        break
                    except:
                        continue
                
                if name_field:
                    driver.execute_script("arguments[0].value = arguments[1]", name_field, name)
                    # Also try to dispatch an input event
                    driver.execute_script("""
                        const event = new Event('input', { bubbles: true });
                        arguments[0].dispatchEvent(event);
                    """, name_field)
                    await ctx.send("Name field filled using XPath.")
                else:
                    await ctx.send("Could not find name field. You may need to enter it manually.")
        except Exception as e:
            await ctx.send(f"Error filling name field: {str(e)}")
        
        # Fill ticker field with similar approach
        try:
            ticker_field = None
            if driver.execute_script("return arguments[0] !== null", form_fields['ticker']):
                ticker_field = form_fields['ticker']
                driver.execute_script("arguments[0].value = arguments[1]", ticker_field, ticker)
                await ctx.send("Ticker field filled via JavaScript.")
            else:
                selectors = [
                    "//input[@placeholder='add a coin ticker (e.g. DOGE)']",
                    "//input[contains(@placeholder, 'ticker')]",
                    "//input[contains(@placeholder, 'DOGE')]",
                    "//input[contains(@id, 'ticker')]",
                    "//input[contains(@class, 'ticker')]"
                ]
                
                for selector in selectors:
                    try:
                        ticker_field = WebDriverWait(driver, 2).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        break
                    except:
                        continue
                
                if ticker_field:
                    driver.execute_script("arguments[0].value = arguments[1]", ticker_field, ticker)
                    driver.execute_script("""
                        const event = new Event('input', { bubbles: true });
                        arguments[0].dispatchEvent(event);
                    """, ticker_field)
                    await ctx.send("Ticker field filled using XPath.")
                else:
                    await ctx.send("Could not find ticker field. You may need to enter it manually.")
        except Exception as e:
            await ctx.send(f"Error filling ticker field: {str(e)}")
        
        # Fill description field
        try:
            desc_field = None
            if driver.execute_script("return arguments[0] !== null", form_fields['description']):
                desc_field = form_fields['description']
                driver.execute_script("arguments[0].value = arguments[1]", desc_field, description)
                await ctx.send("Description field filled via JavaScript.")
            else:
                selectors = [
                    "//textarea[@placeholder='write a short description']",
                    "//textarea[contains(@placeholder, 'description')]",
                    "//textarea"
                ]
                
                for selector in selectors:
                    try:
                        desc_field = WebDriverWait(driver, 2).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        break
                    except:
                        continue
                
                if desc_field:
                    driver.execute_script("arguments[0].value = arguments[1]", desc_field, description)
                    driver.execute_script("""
                        const event = new Event('input', { bubbles: true });
                        arguments[0].dispatchEvent(event);
                    """, desc_field)
                    await ctx.send("Description field filled using XPath.")
                else:
                    await ctx.send("Could not find description field. You may need to enter it manually.")
        except Exception as e:
            await ctx.send(f"Error filling description field: {str(e)}")
        
        # Download and upload image if we have an image URL
        if image_url:
            try:
                await ctx.send("Downloading image from Discord...")
                
                temp_dir = Path(tempfile.gettempdir()) / "discord_images"
                temp_dir.mkdir(exist_ok=True)
                
                image_filename = f"memecoin_image_{int(time.time())}.png"
                image_path = temp_dir / image_filename
                
                # Download using urllib
                urllib.request.urlretrieve(image_url, image_path)
                
                await ctx.send(f"Image downloaded to {image_path}")
                
                # Try different approaches to find upload field
                # First try direct JavaScript to find upload button
                script = """
                function findImageUploadElement() {
                    // Look for file input
                    const fileInputs = document.querySelectorAll('input[type="file"]');
                    if (fileInputs.length > 0) return fileInputs[0];
                    
                    // Look for buttons that might trigger file upload
                    const uploadTexts = ['upload', 'image', 'logo', 'picture', 'photo'];
                    const buttons = document.querySelectorAll('button, div[role="button"], span[role="button"], a[role="button"]');
                    
                    for (let btn of buttons) {
                        const text = btn.innerText.toLowerCase();
                        if (uploadTexts.some(t => text.includes(t))) {
                            return btn;
                        }
                    }
                    
                    // Look for image placeholders/dropzones
                    const imagePlaceholders = document.querySelectorAll('div[class*="image"], div[class*="upload"], div[class*="logo"]');
                    if (imagePlaceholders.length > 0) return imagePlaceholders[0];
                    
                    return null;
                }
                
                return findImageUploadElement();"""
                
                
                upload_element = driver.execute_script(script)
                
                if upload_element:
                    await ctx.send("Found upload element via JavaScript, clicking it...")
                    driver.execute_script("arguments[0].click();", upload_element)
                    time.sleep(1)
                
                # Now try to find file input that may have appeared
                file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                
                if file_inputs:
                    await ctx.send("Found file input, uploading image...")
                    file_inputs[0].send_keys(str(image_path.absolute()))
                    await ctx.send("Image uploaded successfully!")
                else:
                    # Try clicking on additional elements that might be upload buttons
                    upload_elements = driver.find_elements(By.XPATH, 
                        "//*[contains(text(), 'Upload') or contains(text(), 'Image') or contains(text(), 'Logo')]")
                    
                    if upload_elements:
                        await ctx.send("Found potential upload button, clicking it...")
                        driver.execute_script("arguments[0].click();", upload_elements[0])
                        time.sleep(2)
                        
                        # Check again for file inputs
                        file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                        if file_inputs:
                            file_inputs[0].send_keys(str(image_path.absolute()))
                            await ctx.send("Image uploaded after clicking upload button!")
                        else:
                            await ctx.send("Couldn't find file input. You may need to upload manually.")
                            await ctx.send(f"Local image saved at: {image_path}")
                    else:
                        await ctx.send("Could not find image upload element. You may need to upload manually.")
                        await ctx.send(f"Local image saved at: {image_path}")
            except Exception as e:
                await ctx.send(f"Error downloading/uploading image: {str(e)}")
                await ctx.send(f"Please manually save and upload the image from: {image_url}")
        
        # Verify form values were actually set
        await ctx.send("Verifying form values...")
        try:
            time.sleep(1)  # Give page a moment to update
            
            # Run a script to check if values were properly set
            verify_script = """
            function verifyFormValues(expectedName, expectedTicker) {
                const inputs = document.querySelectorAll('input');
                let nameSet = false;
                let tickerSet = false;
                
                for (let input of inputs) {
                    if (input.value === expectedName) {
                        nameSet = true;
                    }
                    if (input.value === expectedTicker) {
                        tickerSet = true;
                    }
                }
                
                // Check textarea for description
                const textareas = document.querySelectorAll('textarea');
                let descSet = false;
                for (let textarea of textareas) {
                    if (textarea.value && textarea.value.length > 0) {
                        descSet = true;
                        break;
                    }
                }
                
                return { nameSet, tickerSet, descSet };
            }
            
            return verifyFormValues(arguments[0], arguments[1]);"""
            
            
            verification = driver.execute_script(verify_script, name, ticker)
            
            # If any fields weren't set properly, try once more with direct keystrokes
            if not verification['nameSet'] or not verification['tickerSet'] or not verification['descSet']:
                await ctx.send("Some fields may not be properly set. Trying alternative method...")
                
                # Alternative method with direct key actions
                if not verification['nameSet']:
                    try:
                        name_inputs = driver.find_elements(By.XPATH, "//input")
                        if name_inputs:
                            # Try the first few inputs
                            for inp in name_inputs[:3]:
                                inp.clear()
                                inp.send_keys(name)
                                inp.send_keys(Keys.TAB)  # Tab to next field
                            await ctx.send("Alternative name filling attempted.")
                    except:
                        pass
                        
                if not verification['tickerSet']:
                    try:
                        ticker_inputs = driver.find_elements(By.XPATH, "//input")
                        if ticker_inputs and len(ticker_inputs) > 1:
                            # Try second input for ticker
                            ticker_inputs[1].clear()
                            ticker_inputs[1].send_keys(ticker)
                            ticker_inputs[1].send_keys(Keys.TAB)
                            await ctx.send("Alternative ticker filling attempted.")
                    except:
                        pass
                        
                if not verification['descSet']:
                    try:
                        desc_inputs = driver.find_elements(By.XPATH, "//textarea")
                        if desc_inputs:
                            desc_inputs[0].clear()
                            desc_inputs[0].send_keys(description)
                            await ctx.send("Alternative description filling attempted.")
                    except:
                        pass
            else:
                await ctx.send("All form fields verified to be properly set!")
        except Exception as e:
            await ctx.send(f"Error during verification: {str(e)}")
        
        # Look for submit button but don't click it automatically
        create_buttons = driver.find_elements(By.XPATH, 
            "//button[contains(text(), 'Create') or contains(text(), 'Submit') or contains(text(), 'Launch') or contains(text(), 'Mint')]")
        
        if create_buttons:
            await ctx.send(f"Found {len(create_buttons)} potential submit button(s). You can click it when ready.")
        else:
            await ctx.send("Could not find a submit button. You may need to submit manually.")
        
        await ctx.send("✅ Form filling complete! Browser will remain open so you can review and submit.")
        await ctx.send(f"If any fields were not filled correctly, here are the values to enter manually:\nName: {name}\nTicker: {ticker}\nDescription: {description}")
        
    except Exception as e:
        await ctx.send(f"Error during automation: {str(e)}")
        await ctx.send("Opening pump.fun manually as fallback...")
        await ctx.send(f"Please manually fill out the form with:\nName: {name}\nTicker: {ticker}\nDescription: {description}")
# Modified MemeCoin Button for pump.fun integration
class MemeCoinButton(Button):
    def __init__(self, embed_content, image_url=None):
        super().__init__(style=discord.ButtonStyle.primary, label="Generate & Create Meme Coin", custom_id=f"memecoin_{int(time.time())}")
        self.embed_content = embed_content
        self.image_url = image_url
    
    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=False, thinking=True)
        
        # Generate memecoin using Gemini AI
        memecoin = await generate_memecoin(self.embed_content)
        
        # Create an embed for the response
        response_embed = discord.Embed(
            title=f"🚀 {memecoin['name']} ({memecoin['ticker']})",
            description=memecoin['description'],
            color=0xfaa61a
        )
        
        # Add the image from the original embed if available
        if self.image_url:
            response_embed.set_image(url=self.image_url)
            
        response_embed.set_footer(text=f"Generated based on embed content • {interaction.user.name}")
        
        await interaction.followup.send(embed=response_embed)
        
        # Now send to pump.fun for token creation
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
    # MODIFIED: Only process messages in the specified channel
    if str(message.channel.id) == MEMECOIN_BUTTON_CHANNEL_ID:
        # Process only messages from webhooks or bots (our relay system)
        if message.webhook_id or message.author.bot:
            # Only care about messages with embeds
            if message.embeds:
                for embed in message.embeds:
                    # Generate a unique ID for this embed
                    embed_id = f"{message.channel.id}_{message.id}_{embed.title}"
                    
                    # Only process if we haven't seen this embed before
                    if embed_id not in processed_embeds:
                        processed_embeds[embed_id] = True
                        
                        # Extract embed content for Gemini AI
                        embed_content = await extract_embed_content(embed)
                        
                        # Get image URL from embed if present
                        image_url = get_embed_image_url(embed)
                        
                        # Create button view with image URL
                        view = View(timeout=None)
                        view.add_item(MemeCoinButton(embed_content, image_url))
                        
                        # Reply to the embed message with our button
                        try:
                            await message.reply(view=view)
                            logging.info(f"Added meme coin button to embed in channel {message.channel.id}: {embed.title}")
                        except Exception as e:
                            logging.error(f"Failed to add button: {e}")
    
    await bot.process_commands(message)

@bot.command(name='createtoken')
async def create_token(ctx, name: str, ticker: str, description: str):
    """Manual command to create a token on pump.fun"""
    await create_token_on_pump(ctx, name, ticker, description)

def relay_messages():
    """Main function to start monitoring all channels."""
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
    """Start the Discord bot."""
    try:
        await bot.start(BOT_TOKEN)
    except Exception as e:
        logging.error(f"Error starting bot: {e}")

if __name__ == "__main__":
    # Start relay in a separate thread
    relay_thread = threading.Thread(target=relay_messages, daemon=True)
    relay_thread.start()
    
    # Start bot in the main thread
    asyncio.run(start_bot())
