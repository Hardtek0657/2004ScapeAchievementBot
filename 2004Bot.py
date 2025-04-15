import requests
from bs4 import BeautifulSoup
import json
import os
from discord_webhook import DiscordWebhook
import time
import logging
from datetime import datetime
from dotenv import load_dotenv, set_key
import discord
from discord.ext import commands, tasks
from typing import Dict, List, Optional
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = sys.stderr = io.TextIOWrapper(
        sys.stdout.buffer, encoding='utf-8', errors='replace'
    )

# Load environment variables
load_dotenv()

# Constants
SKILLS = [
    "agility", "attack", "cooking", "crafting", "defence",
    "firemaking", "fishing", "fletching", "herblore", "hitpoints",
    "magic", "mining", "prayer", "ranged", "runecrafting",
    "smithing", "strength", "thieving", "woodcutting"
]

CONFIG = {
    'WEBHOOK_URL': os.getenv('WEBHOOK_URL'),
    'DISCORD_TOKEN': os.getenv('DISCORD_TOKEN'),
    'PLAYERS_TO_TRACK': [p.strip() for p in os.getenv('PLAYERS_TO_TRACK', '').split(',') if p.strip()],
    'ADVENTURE_LOG_FILE': os.getenv('ADVENTURE_LOG_FILE', 'adventure_logs.json'),
    'BASE_URL': os.getenv('BASE_URL', 'https://2004.lostcity.rs/player/adventurelog/'),
    'LEVELS_DIR': "player_levels"
}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class AdventureLogMonitor:
    def __init__(self):
        self.ensure_dirs()
        self.skill_assets = {
            "agility": {"emoji": "<:icon_2_2:1361178696819671140>", "avatar": "https://7db.pw/dcbe.png"},
            "attack": {"emoji": "<:icon_1_1:1361178692214325258>", "avatar": "https://7db.pw/854af639.png"},
            "cooking": {"emoji": "<:icon_4_3:1361178836116701256>", "avatar": "https://7db.pw/35d05.png"},
            "crafting": {"emoji": "<:icon_5_2:1361178838918496407>", "avatar": "https://7db.pw/daa5.png"},
            "defence": {"emoji": "<:icon_3_1:1361178761382592676>", "avatar": "https://7db.pw/27cd4cd.png"},
            "firemaking": {"emoji": "<:icon_5_3:1361178839627333723>", "avatar": "https://7db.pw/156f5a33.png"},
            "fishing": {"emoji": "<:icon_3_3:1361178764108890200>", "avatar": "https://7db.pw/816ab403.png"},
            "fletching": {"emoji": "<:icon_6_2:1361178871470362814>", "avatar": "https://7db.pw/720c.png"},
            "herblore": {"emoji": "<:icon_3_2:1361178762464464907>", "avatar": "https://7db.pw/8c09c5b.png"},
            "hitpoints": {"emoji": "<:icon_1_2:1361178693195792414>", "avatar": "https://7db.pw/5f44d3bc.png"},
            "magic": {"emoji": "<:icon_6_1:1361178869549498501>", "avatar": "https://7db.pw/b26eb0.png"},
            "mining": {"emoji": "<:icon_1_3:1361178694382784635>", "avatar": "https://7db.pw/1a5ad7.png"},
            "prayer": {"emoji": "<:icon_5_1:1361178838012399636>", "avatar": "https://7db.pw/386e7150.png"},
            "ranged": {"emoji": "<:icon_4_1:1361178765161533490>", "avatar": "https://7db.pw/bf0c8794.png"},
            "runecrafting": {"emoji": "<:icon_7_1:1361178874276483264>", "avatar": "https://7db.pw/ec0e.png"},
            "smithing": {"emoji": "<:icon_2_3:1361178760166117427>", "avatar": "https://7db.pw/59afd783.png"},
            "strength": {"emoji": "<:icon_2_1:1361178695473303693>", "avatar": "https://7db.pw/dee41.png"},
            "thieving": {"emoji": "<:icon_4_2:1361178834971660439>", "avatar": "https://7db.pw/6d4491.png"},
            "woodcutting": {"emoji": "<:icon_6_3:1361178872691036337>", "avatar": "https://7db.pw/b7dfd8bf.png"},
            "event": {"emoji": "<:icon_event_1_1:1361354881725890682>", "avatar": "http://7db.pw/a162767.jpg"},
            "quest": {"emoji": "<:icon_quest_1_1:1361369660141998360>", "avatar": "http://7db.pw/f7232a.png"},
            "clue": {"emoji": "<:icon_clue_1_1:1361377846743924836>", "avatar": "http://7db.pw/c4b6e.png"},
            "default": {"emoji": "⏱️", "avatar": "https://2004.lostcity.rs/img/logo_small.png"}
        }

    def ensure_dirs(self):
        os.makedirs(CONFIG['LEVELS_DIR'], exist_ok=True)

    def get_level_file(self, username: str) -> str:
        return os.path.join(CONFIG['LEVELS_DIR'], f"{username.lower()}_levels.json")

    def load_data(self, file_path: str, default=None):
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
            return default if default is not None else {}
        except Exception as e:
            logger.error(f"Error loading {file_path}: {str(e)}")
            return default if default is not None else {}

    def save_data(self, file_path: str, data):
        try:
            # Only create directories if there are any in the path
            dir_path = os.path.dirname(file_path)
            if dir_path:  # Only create directories if dir_path is not empty
                os.makedirs(dir_path, exist_ok=True)

            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving {file_path}: {str(e)}")
            return False

    def fetch_player_logs(self, username: str) -> List[Dict]:
        try:
            response = requests.get(
                f"{CONFIG['BASE_URL']}{username}",
                headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"},
                timeout=15
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            return [
                parsed_entry
                for entry in soup.find_all("div", style="text-align: left")
                if (parsed_entry := self.parse_log_entry(entry))
            ]
        except requests.RequestException as e:
            logger.error(f"Network error fetching {username}: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing {username}: {str(e)}")
        return []

    def parse_log_entry(self, entry) -> Optional[Dict]:
        try:
            timestamp = entry.find("span").get_text(strip=True)
            message = next((br.next_sibling.strip() for br in entry.find_all("br")
                          if br.next_sibling and isinstance(br.next_sibling, str)),
                          entry.get_text().split('\n')[-1].strip())
            return {"timestamp": timestamp, "message": message}
        except Exception:
            return None

    def detect_skill(self, message: str) -> str:
        message_lower = message.lower()

        # Check special cases first (most common patterns)
        if "quest complete" in message_lower:
            return "quest"
        if "failed random event" in message_lower:
            return "event"
        if "clue scroll" in message_lower:
            return "clue"

        # Optimized skill check using any() with generator
        found_skill = next((skill for skill in SKILLS if skill in message_lower), None)
        return found_skill if found_skill else "default"

    def update_levels(self, username: str, log_entry: str) -> bool:
        levels = self.load_data(self.get_level_file(username), {s: 1 for s in SKILLS})
        if "Levelled up" not in log_entry:
            return False

        parts = log_entry.split()
        try:
            skill = parts[parts.index("Levelled") + 2].lower().rstrip(',')
            new_level = int(parts[parts.index("to") + 1])
            if skill in levels and new_level > levels[skill]:
                levels[skill] = new_level
                return self.save_data(self.get_level_file(username), levels)
        except (ValueError, IndexError):
            logger.debug(f"Couldn't parse level-up: {log_entry}")
        return False

    def calculate_combat_level(self, levels: Dict) -> int:
        try:
            base = 0.25 * (levels.get("defence", 1) + levels.get("hitpoints", 1) + (levels.get("prayer", 1) // 2))
            melee = 0.325 * (levels.get("attack", 1) + levels.get("strength", 1))
            ranged = 0.325 * (levels.get("ranged", 1) * 1.5)
            magic = 0.325 * (levels.get("magic", 1) * 1.5)
            return int(max(base + melee, base + ranged, base + magic))
        except Exception:
            return 0

    def send_discord_update(self, username: str, entries: List[Dict]):
        if not entries:
            return

        latest_entry = entries[-1]['message']
        latest_skill = self.detect_skill(latest_entry)
        assets = self.skill_assets.get(latest_skill, self.skill_assets["default"])

        # Pre-compute base username to avoid repetition
        base_username = f"{username} → "

        # Determine display text using a dictionary lookup (O(1) complexity)
        skill_display = {
            "event": "Random Event!",
            "quest": "Quest Update!",
            "clue": "Clue Update!"
        }.get(latest_skill)

        if skill_display:
            username_display = base_username + skill_display
        elif latest_entry.startswith("Levelled up"):
            # Efficient level extraction using partition
            _, _, level_part = latest_entry.partition(" to ")
            if level_part:
                username_display = f"{username} {latest_skill.title()} → {level_part.split()[0]}"
            else:
                username_display = f"{username} {latest_skill.title()}"
        else:
            username_display = f"{username} {latest_skill.title()}"

        # Build embed more efficiently
        embed_fields = []
        for date, date_entries in self.group_entries_by_date(entries).items():
            field_value = "\n".join(
                f"{self.skill_assets.get(self.detect_skill(e['message']), {}).get('emoji', '⏱️')} "
                f"**{e['timestamp'].split(' ')[1]}** - {e['message']}"
                for e in date_entries
            )
            embed_fields.append({
                "name": f"🗓️ {date}",
                "value": field_value,
                "inline": False
            })

        webhook = DiscordWebhook(
            url=CONFIG['WEBHOOK_URL'],
            username=username_display,
            avatar_url=assets["avatar"]
        )

        webhook.add_embed({
            "title": f"📜 {username}'s Adventure Log Updates",
            "color": 0x3498db,
            "fields": embed_fields,
            "footer": {"text": f"Updated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        })

        try:
            webhook.execute()
        except Exception as e:
            logger.error(f"Failed to send webhook for {username}: {str(e)}")

    def group_entries_by_date(self, entries: List[Dict]) -> Dict:
        grouped = {}
        for entry in entries:
            date = entry['timestamp'].split(' ')[0]
            grouped.setdefault(date, []).append(entry)
        return grouped

    def monitor_player(self, username: str):
        saved_logs = self.load_data(CONFIG['ADVENTURE_LOG_FILE'], {}).get(username, [])
        current_logs = self.fetch_player_logs(username)

        if not current_logs:
            return

        last_known_time = max((e['timestamp'] for e in saved_logs), default="")
        new_entries = [e for e in current_logs if e['timestamp'] > last_known_time]

        if new_entries:
            for entry in new_entries:
                self.update_levels(username, entry['message'])
            self.send_discord_update(username, new_entries)
            self.save_data(
                CONFIG['ADVENTURE_LOG_FILE'],
                {**self.load_data(CONFIG['ADVENTURE_LOG_FILE'], {}), username: current_logs}
            )

monitor = AdventureLogMonitor()

# Discord Commands
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")
    monitoring_loop.start()

@tasks.loop(seconds=3.0)
async def monitoring_loop():
    for player in CONFIG['PLAYERS_TO_TRACK']:
        monitor.monitor_player(player)

@bot.command()
async def track(ctx, username: str):
    if username in CONFIG['PLAYERS_TO_TRACK']:
        await ctx.send(f"{username} is already tracked.")
        return

    CONFIG['PLAYERS_TO_TRACK'].append(username)
    set_key('.env', 'PLAYERS_TO_TRACK', ','.join(CONFIG['PLAYERS_TO_TRACK']))
    monitor.load_data(monitor.get_level_file(username), {s: 1 for s in SKILLS})
    await ctx.send(f"Now tracking {username}.")

@bot.command()
async def untrack(ctx, username: str):
    if username not in CONFIG['PLAYERS_TO_TRACK']:
        await ctx.send(f"{username} is not being tracked.")
        return

    CONFIG['PLAYERS_TO_TRACK'].remove(username)
    set_key('.env', 'PLAYERS_TO_TRACK', ','.join(CONFIG['PLAYERS_TO_TRACK']))
    await ctx.send(f"Stopped tracking {username}.")

@bot.command()
async def list(ctx):
    if not CONFIG['PLAYERS_TO_TRACK']:
        await ctx.send("No players being tracked.")
        return

    await ctx.send("**Tracked Players:**\n" + "\n".join(f"• {p}" for p in CONFIG['PLAYERS_TO_TRACK']))

@bot.command()
async def force_check(ctx, username: str):
    saved_logs = monitor.load_data(CONFIG['ADVENTURE_LOG_FILE'], {}).get(username, [])
    current_logs = monitor.fetch_player_logs(username)

    if not current_logs:
        await ctx.send(f"Could not fetch logs for {username}.")
        return

    new_entries = [e for e in current_logs if e['timestamp'] > max((e['timestamp'] for e in saved_logs), default="")]

    if new_entries:
        for entry in new_entries:
            monitor.update_levels(username, entry['message'])
        monitor.send_discord_update(username, new_entries)
        monitor.save_data(
            CONFIG['ADVENTURE_LOG_FILE'],
            {**monitor.load_data(CONFIG['ADVENTURE_LOG_FILE'], {}), username: current_logs}
        )
        await ctx.send(f"Found {len(new_entries)} new entries for {username}.")
    else:
        await ctx.send(f"No new entries found for {username}.")

@bot.command()
async def get_logs(ctx, username: str, limit: int = 5):
    logs = monitor.load_data(CONFIG['ADVENTURE_LOG_FILE'], {}).get(username, [])

    if not logs:
        await ctx.send(f"No logs found for {username}.")
        return

    recent_logs = logs[-limit:] if limit > 0 else logs
    recent_logs.reverse()

    response = f"**Recent logs for {username}:**\n" + "\n".join(
        f"**{entry['timestamp']}** - {entry['message']}"
        for entry in recent_logs
    )

    await ctx.send(response[:2000])

@bot.command()
async def levels(ctx, username: str):
    """Get a player's current skill levels with combat skills first."""
    levels = monitor.load_data(monitor.get_level_file(username), {s: 1 for s in SKILLS})

    # Skill data with emojis and combat skill priority
    SKILL_DATA = {
        # Combat skills (ordered by importance)
        "attack": {"emoji": "<:icon_1_1:1361178692214325258>", "priority": 1},
        "strength": {"emoji": "<:icon_2_1:1361178695473303693>", "priority": 2},
        "defence": {"emoji": "<:icon_3_1:1361178761382592676>", "priority": 3},
        "hitpoints": {"emoji": "<:icon_1_2:1361178693195792414>", "priority": 4},
        "ranged": {"emoji": "<:icon_4_1:1361178765161533490>", "priority": 5},
        "magic": {"emoji": "<:icon_6_1:1361178869549498501>", "priority": 6},
        "prayer": {"emoji": "<:icon_5_1:1361178838012399636>", "priority": 7},
        # Other skills (alphabetical)
        "agility": {"emoji": "<:icon_2_2:1361178696819671140>", "priority": 8},
        "cooking": {"emoji": "<:icon_4_3:1361178836116701256>", "priority": 8},
        "crafting": {"emoji": "<:icon_5_2:1361178838918496407>", "priority": 8},
        "firemaking": {"emoji": "<:icon_5_3:1361178839627333723>", "priority": 8},
        "fishing": {"emoji": "<:icon_3_3:1361178764108890200>", "priority": 8},
        "fletching": {"emoji": "<:icon_6_2:1361178871470362814>", "priority": 8},
        "herblore": {"emoji": "<:icon_3_2:1361178762464464907>", "priority": 8},
        "mining": {"emoji": "<:icon_1_3:1361178694382784635>", "priority": 8},
        "runecrafting": {"emoji": "<:icon_7_1:1361178874276483264>", "priority": 8},
        "smithing": {"emoji": "<:icon_2_3:1361178760166117427>", "priority": 8},
        "thieving": {"emoji": "<:icon_4_2:1361178834971660439>", "priority": 8},
        "woodcutting": {"emoji": "<:icon_6_3:1361178872691036337>", "priority": 8}
    }

    # Calculate totals
    total_level = sum(levels.values())
    combat_level = monitor.calculate_combat_level(levels)

    # Create embed
    embed = discord.Embed(
        title=f"{username}'s Skill Levels",
        color=discord.Color.blue()
    )

    # Add totals at the top
    embed.add_field(
        name="📊 Totals",
        value=f"✨ **Total Level:** {total_level}\n"
              f"⚔️ **Combat Level:** {combat_level}",
        inline=False
    )

    # Sort skills: combat first (by priority), then others by level (high to low)
    sorted_skills = sorted(
        levels.items(),
        key=lambda x: (
            SKILL_DATA.get(x[0].lower(), {}).get("priority", 9),
            -x[1],
            x[0]
        )
    )

    # Separate combat and non-combat skills
    combat_skills = ["attack", "strength", "defence", "hitpoints", "ranged", "magic", "prayer"]
    combat_lines = []
    other_lines = []

    for skill, level in sorted_skills:
        emoji = SKILL_DATA.get(skill.lower(), {}).get("emoji", "")
        # Format with fixed width for perfect alignment
        line = f"{emoji} `{skill.title():<11}` `{level:>2}`"
        if skill.lower() in combat_skills:
            combat_lines.append(line)
        else:
            other_lines.append(line)

    # Function to format lines in groups of 3 with perfect spacing
    def format_skill_lines(skill_lines):
        formatted = []
        for i in range(0, len(skill_lines), 3):
            group = skill_lines[i:i+3]
            # Use 4 spaces between columns for perfect alignment
            formatted.append("    ".join(group))
        return "\n".join(formatted)

    # Add combat skills section
    if combat_lines:
        embed.add_field(
            name="⚔️ Combat Skills",
            value=format_skill_lines(combat_lines),
            inline=False
        )

    # Add other skills section
    if other_lines:
        embed.add_field(
            name="🔧 Other Skills",
            value=format_skill_lines(other_lines),
            inline=False
        )

    # Set thumbnail to player's highest combat skill
    top_combat_skill = next(
        (skill for skill, _ in sorted_skills if skill.lower() in combat_skills),
        None
    )
    if top_combat_skill:
        embed.set_thumbnail(url=SKILL_DATA.get(top_combat_skill.lower(), {}).get("avatar", ""))

    await ctx.send(embed=embed)

@bot.command()
async def test_level_update(ctx, username: str, skill: str, level: int):
    if skill.lower() not in SKILLS:
        await ctx.send(f"Invalid skill. Valid skills: {', '.join(SKILLS)}")
        return

    levels = monitor.load_data(monitor.get_level_file(username), {s: 1 for s in SKILLS})
    levels[skill.lower()] = level

    if monitor.save_data(monitor.get_level_file(username), levels):
        await ctx.send(f"Set {username}'s {skill} to {level}.")
    else:
        await ctx.send(f"Failed to update {username}'s levels.")

if __name__ == "__main__":
    if not CONFIG['DISCORD_TOKEN']:
        logger.error("Missing Discord token!")
        exit(1)

    try:
        bot.run(CONFIG['DISCORD_TOKEN'])
    except Exception as e:
        logger.critical(f"Bot failed: {str(e)}")
