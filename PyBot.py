import requests
from bs4 import BeautifulSoup
import json
import os
from discord_webhook import DiscordWebhook
import time
import logging
from datetime import datetime

# Config
WEBHOOK_URL = ""
PLAYERS_TO_TRACK = ["CoreStar", "Tomy"]
ADVENTURE_LOG_FILE = "adventure_logs.json"
BASE_URL = "https://2004.lostcity.rs/player/adventurelog/"

# --- Enhanced Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Data Management Functions ---
def load_logs():
    """Load saved logs from JSON file with detailed logging."""
    try:
        logger.debug(f"Attempting to load logs from {ADVENTURE_LOG_FILE}")
        if os.path.exists(ADVENTURE_LOG_FILE):
            with open(ADVENTURE_LOG_FILE, "r") as f:
                data = json.load(f)
                logger.debug(f"Successfully loaded logs. Found data for {len(data)} players")
                return data
        logger.debug("No existing log file found, returning empty dict")
        return {}
    except Exception as e:
        logger.error(f"CRITICAL ERROR loading logs: {str(e)}", exc_info=True)
        return {}

def save_logs(logs):
    """Save logs to JSON file with transaction logging."""
    try:
        logger.debug(f"Preparing to save logs for {len(logs)} players")
        with open(ADVENTURE_LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)
        logger.info(f"Logs successfully saved to {ADVENTURE_LOG_FILE}")
    except Exception as e:
        logger.error(f"FAILED to save logs: {str(e)}", exc_info=True)

def update_logs(username, new_logs):
    """Update logs for a specific player with change tracking."""
    logger.debug(f"Updating logs for {username}")
    old_logs = load_logs()
    old_count = len(old_logs.get(username, []))
    new_count = len(new_logs)

    logs = old_logs.copy()
    logs[username] = new_logs
    save_logs(logs)

    logger.info(f"Updated {username}: {old_count} → {new_count} entries")

# --- Enhanced Parsing Functions ---
def parse_log_entry(entry):
    """Robust log entry parser with detailed error reporting."""
    try:
        logger.debug(f"Parsing entry: {str(entry)[:100]}...")

        # Extract timestamp
        timestamp_span = entry.find("span")
        if not timestamp_span:
            logger.warning("No timestamp span found in entry")
            return None

        timestamp = timestamp_span.get_text(strip=True)
        logger.debug(f"Found timestamp: {timestamp}")

        # Extract message using improved method
        for br in entry.find_all("br"):
            next_s = br.next_sibling
            if next_s and isinstance(next_s, str):
                message = next_s.strip()
                if message:
                    logger.debug(f"Extracted message: {message}")
                    return {
                        "timestamp": timestamp,
                        "message": message
                    }

        # Fallback method if <br> approach fails
        message = entry.get_text().split('\n')[-1].strip()
        logger.debug(f"Used fallback method. Message: {message}")
        return {
            "timestamp": timestamp,
            "message": message
        }

    except Exception as e:
        logger.error(f"FAILED to parse entry: {str(e)}", exc_info=True)
        return None

def fetch_logs(username):
    """Fetch logs with connection and parsing diagnostics."""
    url = f"{BASE_URL}{username}"
    logger.info(f"Fetching logs for {username} from {url}")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }

        logger.debug(f"Sending GET request to {url}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        logger.debug(f"Received response (status {response.status_code})")
        soup = BeautifulSoup(response.text, 'html.parser')

        entries = soup.find_all("div", style="text-align: left")
        logger.debug(f"Found {len(entries)} raw log entries")

        parsed_entries = [parse_log_entry(entry) for entry in entries]
        valid_entries = [entry for entry in parsed_entries if entry]

        logger.info(f"Successfully parsed {len(valid_entries)}/{len(entries)} entries for {username}")
        return valid_entries

    except requests.exceptions.RequestException as e:
        logger.error(f"NETWORK ERROR fetching {username}: {str(e)}")
    except Exception as e:
        logger.error(f"UNEXPECTED ERROR processing {username}: {str(e)}", exc_info=True)
    return None

def compare_logs(old_logs, new_logs):
    """Compare logs with detailed change analysis."""
    if not old_logs:
        logger.debug("No old logs found, treating all as new")
        return new_logs

    if not new_logs:
        logger.warning("Received empty new logs")
        return []

    try:
        last_known_time = max(entry["timestamp"] for entry in old_logs)
        logger.debug(f"Last known timestamp: {last_known_time}")

        new_entries = [
            entry for entry in new_logs
            if entry["timestamp"] > last_known_time
        ]

        logger.info(f"Found {len(new_entries)} new entries since {last_known_time}")
        return new_entries

    except Exception as e:
        logger.error(f"ERROR comparing logs: {str(e)}", exc_info=True)
        return new_logs

# --- Monitoring Functions ---
def detect_skill_type(message):
    """Determine skill type from exact skill name matches."""
    message_lower = message.lower()

    # List of all 19 skills in alphabetical order
    skills = [
        "agility",
        "attack",
        "cooking",
        "crafting",
        "defence",
        "firemaking",
        "fishing",
        "fletching",
        "herblore",
        "hitpoints",
        "magic",
        "mining",
        "prayer",
        "ranged",
        "runecrafting",
        "smithing",
        "strength",
        "thieving",
        "woodcutting"
    ]

    # Check for exact skill name matches
    for skill in skills:
        if skill in message_lower:
            return skill

    # Special case for quests
    if "quest" in message_lower:
        return "quest"

    return "default"

def send_to_discord(username, entries):
    """Discord webhook sender with dynamic avatars and skill/level in username."""
    try:
        logger.debug(f"Preparing Discord message for {username} ({len(entries)} entries)")

        # Complete skill data with emojis and avatar URLs
        SKILL_DATA = {
            "agility": {
                "emoji": "<:icon_2_2:1361178696819671140>",
                "avatar": "https://7db.pw/dcbe.png"
            },
            "attack": {
                "emoji": "<:icon_1_1:1361178692214325258>",
                "avatar": "https://7db.pw/854af639.png"
            },
            "cooking": {
                "emoji": "<:icon_4_3:1361178836116701256>",
                "avatar": "https://7db.pw/35d05.png"
            },
            "crafting": {
                "emoji": "<:icon_5_2:1361178838918496407>",
                "avatar": "https://7db.pw/daa5.png"
            },
            "defence": {
                "emoji": "<:icon_3_1:1361178761382592676>",
                "avatar": "https://7db.pw/27cd4cd.png"
            },
            "firemaking": {
                "emoji": "<:icon_5_3:1361178839627333723>",
                "avatar": "https://7db.pw/156f5a33.png"
            },
            "fishing": {
                "emoji": "<:icon_3_3:1361178764108890200>",
                "avatar": "https://7db.pw/816ab403.png"
            },
            "fletching": {
                "emoji": "<:icon_6_2:1361178871470362814>",
                "avatar": "https://7db.pw/720c.png"
            },
            "herblore": {
                "emoji": "<:icon_3_2:1361178762464464907>",
                "avatar": "https://7db.pw/8c09c5b.png"
            },
            "hitpoints": {
                "emoji": "<:icon_1_2:1361178693195792414>",
                "avatar": "https://7db.pw/5f44d3bc.png"
            },
            "magic": {
                "emoji": "<:icon_6_1:1361178869549498501>",
                "avatar": "https://7db.pw/b26eb0.png"
            },
            "mining": {
                "emoji": "<:icon_1_3:1361178694382784635>",
                "avatar": "https://7db.pw/1a5ad7.png"
            },
            "prayer": {
                "emoji": "<:icon_5_1:1361178838012399636>",
                "avatar": "https://7db.pw/386e7150.png"
            },
            "ranged": {
                "emoji": "<:icon_4_1:1361178765161533490>",
                "avatar": "https://7db.pw/bf0c8794.png"
            },
            "runecrafting": {
                "emoji": "<:icon_7_1:1361178874276483264>",
                "avatar": "https://7db.pw/ec0e.png"
            },
            "smithing": {
                "emoji": "<:icon_2_3:1361178760166117427>",
                "avatar": "https://7db.pw/59afd783.png"
            },
            "strength": {
                "emoji": "<:icon_2_1:1361178695473303693>",
                "avatar": "https://7db.pw/dee41.png"
            },
            "thieving": {
                "emoji": "<:icon_4_2:1361178834971660439>",
                "avatar": "https://7db.pw/6d4491.png"
            },
            "woodcutting": {
                "emoji": "<:icon_6_3:1361178872691036337>",
                "avatar": "https://7db.pw/b7dfd8bf.png"
            },
            "quest": {
                "emoji": "📜",
                "avatar": "https://i.imgur.com/quest_avatar.png"
            },
            "default": {
                "emoji": "⏱️",
                "avatar": "https://2004.lostcity.rs/img/logo_small.png"
            }
        }

        # Determine the most recent skill and level
        latest_skill = "default"
        level_info = ""
        if entries:
            latest_entry = entries[-1]['message']
            latest_skill = detect_skill_type(latest_entry)

            # Extract level information for level up messages
            if latest_entry.startswith("Levelled up"):
                # Extract the new level number (after "to")
                level_parts = latest_entry.split()
                if len(level_parts) >= 5:
                    new_level = level_parts[-1]
                    level_info = f"→ {new_level}"

            # Format username with skill and level
            username_display = f"{username} {latest_skill.title()} {level_info}"
        else:
            username_display = username

        skill_data = SKILL_DATA.get(latest_skill, SKILL_DATA["default"])

        # Create webhook with dynamic avatar and skill/level in username
        webhook = DiscordWebhook(
            url=WEBHOOK_URL,
            username=username_display,
            avatar_url=skill_data["avatar"]
        )

        # Create embed without image
        embed = {
            "title": f"📜 {username}'s Adventure Log Updates",
            "color": 0x3498db,
            "fields": [],
            "footer": {
                "text": f"Last updated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }

        # Group entries by date
        entries_by_date = {}
        for entry in entries:
            date_part = entry['timestamp'].split(' ')[0]
            if date_part not in entries_by_date:
                entries_by_date[date_part] = []
            entries_by_date[date_part].append(entry)

        # Format each date group as a field
        for date, date_entries in entries_by_date.items():
            field_value = ""
            for entry in date_entries:
                time_part = entry['timestamp'].split(' ')[1]  # Full timestamp with seconds
                skill = detect_skill_type(entry['message'])
                skill_emoji = SKILL_DATA.get(skill, SKILL_DATA["default"])["emoji"]
                field_value += f"{skill_emoji} **{time_part}** - {entry['message']}\n"

            embed["fields"].append({
                "name": f"🗓️ {date}",
                "value": field_value.strip(),
                "inline": False
            })

        webhook.add_embed(embed)
        response = webhook.execute()

        if response.status_code == 204:
            logger.info(f"Successfully sent notification for {username}")
        else:
            logger.error(f"Discord API responded with: {response.status_code}")

    except Exception as e:
        logger.error(f"WEBHOOK FAILED: {str(e)}", exc_info=True)

def monitor_player(username):
    """Monitor player with operational telemetry."""
    logger.debug(f"Starting monitoring cycle for {username}")

    try:
        saved_logs = load_logs().get(username, [])
        logger.debug(f"Loaded {len(saved_logs)} saved entries for {username}")

        current_logs = fetch_logs(username)
        if not current_logs:
            logger.warning(f"No logs retrieved for {username}")
            return

        new_entries = compare_logs(saved_logs, current_logs)
        if new_entries:
            logger.info(f"Detected {len(new_entries)} new entries for {username}")
            send_to_discord(username, new_entries)
            update_logs(username, current_logs)
        else:
            logger.debug(f"No new entries found for {username}")

    except Exception as e:
        logger.error(f"MONITORING FAILURE for {username}: {str(e)}", exc_info=True)

# --- Main Loop ---
if __name__ == "__main__":
    logger.info("🚀 Starting Adventure Log Monitor")
    logger.info(f"Tracking players: {', '.join(PLAYERS_TO_TRACK)}")
    logger.info(f"Data will be saved to {ADVENTURE_LOG_FILE}")

    try:
        while True:
            start_time = time.time()
            logger.debug("--- Starting monitoring cycle ---")

            for player in PLAYERS_TO_TRACK:
                monitor_player(player)

            cycle_time = time.time() - start_time
            logger.debug(f"Cycle completed in {cycle_time:.2f} seconds")

            sleep_time = max(0, 3 - cycle_time)
            if sleep_time > 0:
                logger.debug(f"Sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("🛑 Received shutdown signal, stopping gracefully...")
    except Exception as e:
        logger.critical(f"💥 CATASTROPHIC FAILURE: {str(e)}", exc_info=True)
    finally:
        logger.info("🔴 Monitoring service stopped")
