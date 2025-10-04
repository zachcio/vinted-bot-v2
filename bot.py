import os
import random
import asyncio
import aiohttp
import discord
import traceback
from datetime import datetime

# === DANE KONFIGURACYJNE ===
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "1423302324717092905"))
BRD_USER = os.getenv("BRD_USER", "brd-customer-hl_ac83e3ba-zone-residential_proxy1")
BRD_PASS = os.getenv("BRD_PASS", "j5pjiodhdgu3")
BRD_HOST = "brd.superproxy.io"
BRD_PORT = "33335"

# === API Vinted ===
SEARCH_URL = "https://www.vinted.pl/api/v2/catalog/items"
SEARCH_PARAMS = {
    "search_text": "iphone",
    "catalog[]": "3661",
    "brand_ids[]": "54661",
    "order": "newest_first",
    "page": 1,
}
HOME_URL = "https://www.vinted.pl"

# === HEADERS ===
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.vinted.pl/",
    "Origin": "https://www.vinted.pl",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# === FILTRY CENOWE ===
PRICE_RANGES = {
    "iphone 11": (100, 350),
    "iphone 11 pro": (250, 450),
    "iphone 11 pro max": (250, 500),
    "iphone 12": (250, 500),
    "iphone 12 pro": (250, 800),
    "iphone 12 pro max": (250, 900),
    "iphone 12 mini": (250, 500),
    "iphone 13": (300, 900),
    "iphone 13 pro": (300, 1300),
    "iphone 13 pro max": (650, 1550),
    "iphone 13 mini": (300, 850),
    "iphone 14": (400, 1300),
    "iphone 14 pro": (900, 1850),
    "iphone 14 pro max": (1000, 2100),
    "iphone 14 plus": (900, 1850),
    "iphone 15": (1200, 2150),
    "iphone 15 pro": (1800, 3000),
    "iphone 15 pro max": (2300, 3200),
    "iphone 15 plus": (1400, 2250),
}

# === SŁOWA ZABRONIONE ===
FORBIDDEN_WORDS = [
    "case", "etui", "ładowarka", "akcesoria", "krt", "obudowa",
    "szkło", "folia", "kabel", "przewód", "słuchawki",
    "powerbank", "adapter", "uchwyt", "pokrowiec", "holder", "stand", "cover",
    "inpost", "opis", "description", "magsafe", "wallet", "portfel", "plecki",
    "skin", "sticker", "decal", "tempered", "glass", "itool", "tools", "kit",
    "battery", "plug", "dock", "mount", "strap", "band", "pouch", "sleeve", "spare",
    "części", "uszkodzony", "zepsuty", "damaged", "broken",
    "icloud", "simlock", "blokada", "locked", "charger", "cable", "accessory",
    "headphones", "earphones", "screen protector", "protector", "hülle", "hulle",
    "ladegerät", "zubehör", "kopfhörer", "kopfhorer",
    "schutzfolie", "coque", "chargeur", "câble", "accessoire",
    "écouteurs", "protection", "repair", "naprawa", "board",
]

# === GLOBALNE ===
intents = discord.Intents.default()
client = discord.Client(intents=intents)
seen_items = set()
first_run = True
vinted_cookies = None

# === FUNKCJE POMOCNICZE ===
def is_valid_item(title: str, price: int) -> bool:
    title_low = title.lower()
    
    for fw in FORBIDDEN_WORDS:
        if fw.lower() in title_low:
            print(f"🚫 Odrzucono (akcesorium: {fw}): {title}")
            return False

    sorted_models = sorted(PRICE_RANGES.items(), key=lambda x: len(x[0]), reverse=True)
    
    matched_model = None
    best_match_length = 0
    
    for model, (low, high) in sorted_models:
        model_low = model.lower()
        if model_low in title_low:
            if len(model) > best_match_length:
                best_match_length = len(model)
                matched_model = model
                matched_low, matched_high = low, high
    
    if matched_model:
        if matched_low <= price <= matched_high:
            print(f"✅ Pasuje: {title} ({price} PLN -> {matched_model} [{matched_low}-{matched_high}])")
            return True
        else:
            print(f"⚠️ Zły zakres: {title} ({price} PLN) dla {matched_model} [{matched_low}-{matched_high}]")
            return False
    
    print(f"❓ Nieznany model: {title} ({price} PLN)")
    return False

def format_time(created_at) -> str:
    try:
        if not created_at:
            return "??:??"
        if isinstance(created_at, (int, float)):
            return datetime.fromtimestamp(created_at).strftime("%H:%M")
        if isinstance(created_at, str):
            return datetime.fromisoformat(created_at.replace('Z', '+00:00')).strftime("%H:%M")
    except Exception as e:
        print(f"⚠️ Błąd czasu: {e}")
    return "??:??"

async def get_vinted_cookies():
    global vinted_cookies
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(ssl=False)
    proxy_url = f"http://{BRD_HOST}:{BRD_PORT}"
    proxy_auth = aiohttp.BasicAuth(BRD_USER, BRD_PASS)
    
    print("🍪 Pobieram cookies...")
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, headers=HEADERS) as session:
            async with session.get(
                HOME_URL,
                headers={**HEADERS, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"},
                proxy=proxy_url,
                proxy_auth=proxy_auth,
            ) as resp:
                print(f"📡 Status cookies: {resp.status}")
                if resp.status == 200:
                    vinted_cookies = resp.cookies
                    print(f"✅ Pobrano {len(vinted_cookies)} cookies")
                    return True
                else:
                    text = await resp.text()
                    print(f"❌ Błąd cookies {resp.status}: {text[:200]}")
    except Exception as e:
        print(f"❌ Błąd cookies: {e}")
    return False

async def fetch_vinted_items() -> list:
    global vinted_cookies
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        if not vinted_cookies:
            success = await get_vinted_cookies()
            if not success:
                retry_count += 1
                print(f"⚠️ Retry {retry_count}/{max_retries}: Bez cookies")
                await asyncio.sleep(5)
                continue
        
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(ssl=False)
        proxy_url = f"http://{BRD_HOST}:{BRD_PORT}"
        proxy_auth = aiohttp.BasicAuth(BRD_USER, BRD_PASS)
        
        try:
            async with aiohttp.ClientSession(
                headers=HEADERS, connector=connector, timeout=timeout, cookies=vinted_cookies
            ) as session:
                async with session.get(SEARCH_URL, params=SEARCH_PARAMS, proxy=proxy_url, proxy_auth=proxy_auth) as resp:
                    print(f"📡 API status: {resp.status}")
                    
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("items", [])
                        print(f"✅ Pobrano {len(items)} ofert")
                        return items
                    
                    elif resp.status == 401:
                        print("🔄 401 - odświeżam cookies")
                        vinted_cookies = None
                        retry_count += 1
                        await asyncio.sleep(5)
                        continue
                    
                    elif resp.status == 403:
                        print("🚫 403 - blokada, czekam 10s")
                        vinted_cookies = None
                        await asyncio.sleep(10)
                        retry_count += 1
                        continue
                    
                    else:
                        text = await resp.text()
                        print(f"⚠️ Status {resp.status}: {text[:200]}")
                        retry_count += 1
                        
        except Exception as e:
            print(f"❌ Błąd fetch: {e}")
            traceback.print_exc()
            retry_count += 1
            await asyncio.sleep(5)
    
    print("😞 Max retry, brak danych")
    return []

async def check_vinted():
    global first_run
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print(f"❌ Kanał {CHANNEL_ID} nie znaleziony")
        return
    
    print("🟢 Monitorowanie...")

    while not client.is_closed():
        items = await fetch_vinted_items()
        
        if not items:
            print("😞 Brak danych, retry za 15s...")
            await asyncio.sleep(15)
            continue

        if first_run:
            for item in items:
                seen_items.add(item.get("id"))
            print(f"🔄 Zapamiętano {len(seen_items)} ofert")
            first_run = False
            await asyncio.sleep(15)
            continue

        new_items = 0
        for item in items:
            iid = item.get("id")
            if not iid or iid in seen_items:
                continue
            seen_items.add(iid)

            title = item.get("title", "Brak tytułu")
            
            price_info = item.get("price", {})
            try:
                price = int(float(price_info.get("amount", "0")))
            except (ValueError, TypeError):
                price = 0
            
            if not is_valid_item(title, price):
                continue

            url = f"https://www.vinted.pl{item.get('path', '')}"
            created = item.get("created_at") or item.get("photo_uploaded_at")
            time_str = format_time(created)

            photo_url = None
            photos = item.get("photos", [])
            if photos:
                p = photos[0]
                if isinstance(p, dict):
                    photo_url = p.get("url") or p.get("full_size_url")

            try:
                price_int = int(float(item.get("price", {}).get("amount", 0)))
            except (ValueError, TypeError):
                price_int = 0

            embed = discord.Embed(
                title=title[:256],
                url=url,
                description=f"💰 Cena: {price_int} PLN\n⏰ Dodano: {time_str}",
                color=0x00ff00,
            )
            if photo_url:
                embed.set_image(url=photo_url)
            embed.set_footer(text="📱 Vinted Bot")

            await channel.send(embed=embed)
            print(f"📤 Wysłano: {title}")
            new_items += 1
            await asyncio.sleep(1)

        print(f"🎉 Nowe: {new_items}")
        print("⏳ Czekam 15s...")
        await asyncio.sleep(15)

        if random.randint(1, 15) == 1:
            print("🔄 Odświeżam cookies...")
            vinted_cookies = None

@client.event
async def on_ready():
    print(f"✅ Zalogowano: {client.user} (ID: {client.user.id})")
    client.loop.create_task(check_vinted())

@client.event
async def on_error(event, *args, **kwargs):
    print(f"❌ Błąd eventu {event}: {args} {kwargs}")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ BRAK TOKENU! Dodaj zmienną TOKEN!")
        exit(1)
    
    try:
        client.run(TOKEN)
    except KeyboardInterrupt:
        print("🛑 Zatrzymano")
    except Exception as e:
        print(f"💥 Krytyczny błąd: {e}")
        traceback.print_exc()