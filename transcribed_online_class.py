import os
import time
import json
import threading
from datetime import datetime
import re
import urllib.parse
import pyautogui
import io
import queue
import requests
from scipy.signal import resample_poly

pyautogui.FAILSAFE = False  # Prevent crash when mouse is near screen corners

import numpy as np
import warnings
import soundcard as sc
warnings.filterwarnings("ignore", message="data discontinuity in recording")

import soundfile as sf
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

load_dotenv()

# ================= CONFIGURATION =================

CHROME_PROFILE_PATH = os.getenv("CHROME_PROFILE_PATH", r"Your class chrome profile path")
PROFILE_DIRECTORY = os.getenv("PROFILE_DIRECTORY", "Default")

KAGGLE_SERVER_URL = os.getenv("KAGGLE_SERVER_URL", "http://localhost") # Fallback

CHECK_INTERVAL_SECONDS = 60 

try:
    TIMETABLE = json.loads(os.getenv("TIMETABLE", "{}"))
except json.JSONDecodeError:
    print("Error parsing TIMETABLE from .env. Make sure it is valid JSON.")
    TIMETABLE = {}

# =================================================

STOP_LISTENING = False
AUTO_REPLIED = False
audio_queue = queue.Queue()

USE_PHYSICAL_MICROPHONE = False

def network_sender_worker(driver, platform):
    global STOP_LISTENING, AUTO_REPLIED
    print(f"[Sender Thread] Started. Target Server: {KAGGLE_SERVER_URL}")
    print("Waiting for speaker audio chunks to stream to Kaggle...")
    
    while not STOP_LISTENING:
        try:
            data_24k, ts_display = audio_queue.get(timeout=1)
        except queue.Empty:
            continue
            
        try:
            max_val = np.abs(data_24k).max()
            if max_val < 1e-4:
                continue

            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, data_24k, 24000, format='WAV', subtype='PCM_16')
            wav_buffer.seek(0)
            
            start_time = time.time()
            try:
                response = requests.post(
                    f"{KAGGLE_SERVER_URL}/transcribe", 
                    files={"audio_file": ("audio.wav", wav_buffer, "audio/wav")}, 
                    timeout=20
                )
                
                if response.status_code == 200:
                    result = response.json()
                    text = result.get("text", "")
                    name_found = result.get("Your name found", False)
                    
                    if text:
                        print(f"[{ts_display}] 🗣️ {text}  (GPU Speed: {time.time()-start_time:.2f}s)")
                        
                        if name_found:
                            print("\n*** 🚨 KAGGLE DETECTED NAME 🚨 ***")
                            print("Auto-replying in chat...")
                            msg = "sir mic not working but i am present"
                            if platform == "meet":
                                send_google_meet_message(driver, msg)
                            elif platform == "teams":
                                send_teams_message(driver, msg)
                            AUTO_REPLIED = True
                            
                else:
                    print(f"[{ts_display}] [Network Error] Server returned code: {response.status_code}")
            except requests.exceptions.Timeout:
                print(f"[{ts_display}] [Network Timeout] Kaggle server took too long to respond.")
            except requests.exceptions.ConnectionError:
                print(f"[{ts_display}] [Network Error] Could not connect to {KAGGLE_SERVER_URL}. Is ngrok running?")
                
        except BaseException as e:
            print(f"[Sender Error] {e}")
        finally:
            audio_queue.task_done()
            
    print("[Sender Thread] Exiting properly.")

def recorder_worker():
    global STOP_LISTENING
    chunk_duration = 6
    sample_rate = 48000
    num_frames = sample_rate * chunk_duration

    while not STOP_LISTENING:
        try:
            speaker = sc.default_speaker()
            mic = sc.get_microphone(id=speaker.id, include_loopback=True)

            print(f"--- Waiter: Recording from {speaker.name} at {sample_rate}Hz ---")

            with mic.recorder(samplerate=sample_rate) as recorder:
                while not STOP_LISTENING:
                    data = recorder.record(numframes=num_frames)

                    if data is not None and hasattr(data, 'shape') and data.size > 0:
                        ts_display = datetime.now().strftime("%H:%M:%S")
                        data_24k = resample_poly(data, up=1, down=2).astype(np.float32)
                        audio_queue.put((data_24k, ts_display))
                    else:
                        time.sleep(0.1)

        except Exception as e:
            err_str = str(e)
            if "0x88890004" in err_str or "0x800401FD" in err_str:
                print("  [Waiter] Windows audio device went to sleep. Rebooting recorder...")
                time.sleep(2)
            else:
                print(f"  [Waiter Error] {e}")
                time.sleep(2)

    print("  [Waiter] Shutting down.")

def send_google_meet_message(driver, message):
    try:
        print("[+] Attempting to send message in Google Meet...")
        selectors = [
            "//textarea[contains(@aria-label, 'Send a message')]",
            "//input[contains(@aria-label, 'Send a message')]",
            "//textarea[@id='chatTextInput']"
        ]
        
        textarea = None
        for sel in selectors:
            try:
                t = driver.find_element(By.XPATH, sel)
                if t.is_displayed():
                    textarea = t
                    break
            except:
                pass
                
        if not textarea:
            try:
                chat_btn = driver.find_element(By.XPATH, "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'chat')]")
                driver.execute_script("arguments[0].click();", chat_btn)
                print("Clicked Google Meet chat button. Waiting for panel to slide open...")
                time.sleep(4)
            except:
                pass 
                
            for sel in selectors:
                try:
                    t = driver.find_element(By.XPATH, sel)
                    if t.is_displayed():
                        textarea = t
                        break
                except:
                    pass
        
        if textarea:
            textarea.send_keys(message)
            time.sleep(0.5)
            textarea.send_keys(Keys.ENTER)
            print("[+] Message sent in Google Meet!")
        else:
            print("[-] Could not locate the Google Meet chat input box.")
            
    except Exception as e:
        print(f"[-] Error sending Google Meet message: {e}")

def send_teams_message(driver, message):
    try:
        print("[+] Attempting to send message in Microsoft Teams...")
        selectors = [
            "//div[@role='textbox' and contains(@aria-label, 'Type a new message')]",
            "//div[@contenteditable='true' and contains(@data-tid, 'chat-input')]",
            "//div[contains(@aria-label, 'message') and @role='textbox']",
            "//div[@role='textbox' and @contenteditable='true']",
            "//div[contains(@class, 'compose')]//div[@contenteditable='true']",
            "//p[contains(@data-placeholder, 'Type a new message')]",
        ]
        
        def find_textbox():
            for sel in selectors:
                try:
                    t = driver.find_element(By.XPATH, sel)
                    if t.is_displayed():
                        return t
                except:
                    pass
            return None
        
        textbox = find_textbox()
                
        if not textbox:
            # Try opening chat panel
            try:
                chat_btn = driver.find_element(By.ID, "chat-button")
                driver.execute_script("arguments[0].click();", chat_btn)
            except:
                try:
                    chat_btn = driver.find_element(By.XPATH, "//button[contains(@aria-label, 'Chat')]")
                    driver.execute_script("arguments[0].click();", chat_btn)
                except:
                    # Last resort: try any button with "chat" in its text
                    try:
                        btns = driver.find_elements(By.TAG_NAME, "button")
                        for b in btns:
                            if "chat" in (b.text or "").lower() and b.is_displayed():
                                driver.execute_script("arguments[0].click();", b)
                                break
                    except:
                        print("Chat button not found in Teams.")
            
            print("Clicked Microsoft Teams chat button. Waiting for panel to render...")
            time.sleep(8)
            
            for attempt in range(3):
                textbox = find_textbox()
                if textbox:
                    break
                print(f"  Chat input not found yet, retrying... ({attempt + 1}/3)")
                time.sleep(3)
        
        if textbox:
            textbox.click()
            time.sleep(0.5)
            textbox.send_keys(message)
            time.sleep(1)
            textbox.send_keys(Keys.ENTER)
            print("[+] Message sent in Teams!")
        else:
            print("[-] Could not locate Microsoft Teams chat input box.")
            
    except Exception as e:
        print(f"[-] Error sending Teams message: {e}")

def get_current_class_info():
    now = datetime.now()
    current_day = now.strftime('%A')
    
    todays_classes = TIMETABLE.get(current_day, [])
    current_time_obj = now.time()
    
    for cls in todays_classes:
        start_time_obj = datetime.strptime(cls['start'], '%H:%M').time()
        end_time_obj = datetime.strptime(cls['end'], '%H:%M').time()
        
        if start_time_obj <= current_time_obj <= end_time_obj:
            env_link_key = cls['env_link']
            gcr_link = os.getenv(env_link_key)
            if not gcr_link or gcr_link.startswith("REPLACE_"):
                print(f"[!] Warning: GCR link for {cls['subject']} not found or not set in .env")
                return None
            return {
                "subject": cls["subject"],
                "gcr_link": gcr_link,
                "end_time": end_time_obj
            }
    return None

def setup_driver():
    chrome_options = Options()
    
    chrome_options.add_argument(f"user-data-dir={CHROME_PROFILE_PATH}")
    chrome_options.add_argument(f"profile-directory={PROFILE_DIRECTORY}")
    
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-features=ExternalProtocolDialog")
    
    prefs = {
        "profile.default_content_setting_values.media_stream_mic": 1,
        "profile.default_content_setting_values.media_stream_camera": 1,
        "profile.default_content_setting_values.notifications": 2,
        "protocol_handler.excluded_schemes": {"msteams": True}, 
        "custom_handlers.enabled": False
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    print("Launching Chrome...")
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def check_if_recent(text, link_url):
    try:
        index = text.find(link_url)
        if index == -1:
            match = re.search(r"(?:meet\.google\.com|zoom\.us/j|teams\.microsoft\.com)[^\s\"'>]+", link_url)
            if match:
                index = text.find(match.group(0))
                
        if index == -1:
            return True 

        snippet = text[:index][-600:] 
        
        lower_snip = snippet.lower()
        if "yesterday" in lower_snip:
            return False
            
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        for month in months:
            if re.search(rf"\b{month}\s+\d{{1,2}}\b", lower_snip) or re.search(rf"\b\d{{1,2}}\s+{month}\b", lower_snip):
                return False

        time_matches = re.findall(r"(\d{1,2}:\d{2}(?:\s*(?:AM|PM|am|pm))?)", snippet)
        if not time_matches:
            return True
            
        post_time_str = time_matches[-1].strip().upper()
        if "AM" in post_time_str or "PM" in post_time_str:
            parsed_time = datetime.strptime(post_time_str, "%I:%M %p").time()
        else:
            parsed_time = datetime.strptime(post_time_str, "%H:%M").time()
        
        now = datetime.now()
        post_dt = datetime.combine(now.date(), parsed_time)
        diff_mins = (now - post_dt).total_seconds() / 60.0
        
        if -10 <= diff_mins <= 20:
            return True
        else:
            print(f"[-] Link is too old or from a past class. Ignoring.")
            return False

    except Exception as e:
        return True

def find_meeting_links(driver, text):
    meet_pattern = r"(?:https://)?meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}"
    zoom_pattern = r"(?:https://)?[\w-]*\.zoom\.us/j/\d+(?:\?pwd=[\w]+)?"
    teams_pattern = r"(?:https://)?teams\.(?:microsoft|live)\.com/(?:l/meetup-join/|meet/)[^\s]+"
    
    seen = set()
    ordered_links = []
    
    def add_link(link_url):
        if link_url:
            if not link_url.startswith("http"):
                link_url = "https://" + link_url
            if link_url not in seen:
                seen.add(link_url)
                ordered_links.append(link_url)
            
    try:
        a_tags = driver.find_elements(By.TAG_NAME, "a")
        for a in a_tags:
            href = a.get_attribute("href")
            if href:
                decoded_href = urllib.parse.unquote(href)
                if "meet.google.com/" in decoded_href or "zoom.us/j/" in decoded_href or "teams.microsoft.com" in decoded_href or "teams.live.com" in decoded_href:
                    add_link(href)
    except Exception as e:
        print(f"Error checking a-tags for links: {e}")

    for match in re.findall(meet_pattern, text): add_link(match)
    for match in re.findall(zoom_pattern, text): add_link(match)
    for match in re.findall(teams_pattern, text): add_link(match)
    
    return ordered_links

def join_google_meet(driver, url):
    print(f"\n[+] Joining Google Meet: {url}")
    driver.get(url)
    
    try:
        wait = WebDriverWait(driver, 15)
        print("Waiting for pre-join screen...")
        time.sleep(5) 
        
        actions = ActionChains(driver)
        print("Turning off Microphone (Ctrl+D)...")
        actions.key_down(Keys.CONTROL).send_keys('d').key_up(Keys.CONTROL).perform()
        time.sleep(2)
        
        print("Turning off Camera (Ctrl+E)...")
        actions.key_down(Keys.CONTROL).send_keys('e').key_up(Keys.CONTROL).perform()
        time.sleep(2)
        
        print("Finding Join button...")
        join_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Join now') or contains(text(), 'Ask to join')]")))
        driver.execute_script("arguments[0].click();", join_button)
        
        print("Successfully clicked the Join button!")
        return True
        
    except Exception as e:
        print(f"[-] Could not join Google Meet automatically. Error: {e}")
        return False

def join_teams_meeting(driver, url):
    print(f"\n[+] Joining Microsoft Teams: {url}")
    driver.get(url)
    guest_name = os.getenv("GUEST_NAME", "Guest User")
    
    try:
        actions = ActionChains(driver)
        
        print("Waiting for 'Open Microsoft Teams' OS popup...")
        time.sleep(3)
        print("Simulating hardware ESCAPE key to dismiss the popup...")
        pyautogui.press('esc')
        time.sleep(2)
        
        print("Looking for 'Continue on this browser' button...")
        time.sleep(3)
        browser_btn = None
        
        try:
            browser_btn = driver.find_element(By.ID, "joinOnWeb")
        except: pass
        
        if not browser_btn:
            try:
                buttons = driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if "Continue on this browser" in btn.text:
                        browser_btn = btn
                        break
            except: pass
        
        if browser_btn:
            print("Found the button! Attempting to click...")
            try:
                browser_btn.click()
            except:
                driver.execute_script("arguments[0].click();", browser_btn)
            print("Selected 'Continue on this browser'.")
        else:
            print("[!] Could not find 'Continue on this browser'. Proceeding anyway...")
        
        print("Waiting for Teams pre-join screen (this can take up to 25 seconds)...")
        time.sleep(25)
        
        print("Checking if Guest Name input is required...")
        try:
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                placeholder = inp.get_attribute("placeholder")
                if placeholder and "Type your name" in placeholder:
                    print(f"Guest mode detected. Entering name '{guest_name}'...")
                    inp.click()
                    inp.clear()
                    inp.send_keys(guest_name)
                    time.sleep(1)
                    break
        except Exception:
            pass
        
        try:
            driver.find_element(By.TAG_NAME, "body").click()
        except: pass
        
        print("Turning off Microphone (Ctrl+Shift+M)...")
        actions.key_down(Keys.CONTROL).key_down(Keys.SHIFT).send_keys('m').key_up(Keys.SHIFT).key_up(Keys.CONTROL).perform()
        time.sleep(3)
        
        print("Turning off Camera (Ctrl+Shift+O)...")
        actions.key_down(Keys.CONTROL).key_down(Keys.SHIFT).send_keys('o').key_up(Keys.SHIFT).key_up(Keys.CONTROL).perform()
        time.sleep(3)
        
        print("Finding Join button...")
        join_btn = None
        try:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "Join" in btn.text or "Join now" in btn.text:
                    join_btn = btn
                    break
        except: pass
        
        if join_btn:
            try:
                join_btn.click()
            except:
                driver.execute_script("arguments[0].click();", join_btn)
            print("Successfully clicked the Teams Join button!")
        else:
            print("[!] Could not find Join button.")
        
        print("Teams page loaded. Keeping browser open until class ends.")
        return True
        
    except Exception as e:
        print(f"[-] Could not interact with Teams automatically. Error: {e}")
        return False

def main():
    global STOP_LISTENING
    print("==================================================")
    print("   Google Classroom Auto-Joiner Started")
    print("==================================================")
    
    print("Make sure your normal Chrome windows are CLOSED.")
    
    try:
        while True:
            current_class = get_current_class_info()
            now = datetime.now()
            
            if not current_class:
                print(f"\n[{now.strftime('%H:%M:%S')}] No class currently active. Sleeping for 1 minute...")
                time.sleep(60)
                continue
                
            print(f"\n[{now.strftime('%H:%M:%S')}] Active class found: {current_class['subject']}. Class ends at {current_class['end_time'].strftime('%H:%M')}.")
            
            try:
                driver = setup_driver()
            except Exception as e:
                print(f"\n[!] Failed to start Chrome. Make sure Chrome is totally closed and profile path is correct.\nError: {e}")
                time.sleep(60)
                continue

            processed_links = set()
            first_run = True
            class_ended_flag = False
            
            try:
                while True:
                    if datetime.now().time() > current_class["end_time"]:
                        print(f"\n[!] Class {current_class['subject']} has ended. Closing Chrome.")
                        class_ended_flag = True
                        break
                        
                    current_time = time.strftime('%H:%M:%S')
                    print(f"\n[{current_time}] Refreshing Google Classroom stream for {current_class['subject']}...")
                    
                    driver.get(current_class["gcr_link"])
                    time.sleep(10)
                    driver.execute_script("window.scrollTo(0, 500);")
                    time.sleep(2)
                    
                    page_text = driver.find_element(By.TAG_NAME, "body").text
                    links = find_meeting_links(driver, page_text)
                    
                    links_to_test = []
                    
                    if first_run:
                        print(f"[*] Initial scan complete. Found {len(links)} existing links on the wall.")
                        for link in links:
                            processed_links.add(link)
                            
                        if links:
                            print("\n[*] Validating links from the initial scan...")
                            first_link = links[0]
                            if check_if_recent(page_text, first_link):
                                print(f"[+] Link matches day & time constraint. Testing: {first_link}")
                                links_to_test.append(first_link)
                            else:
                                print("[-] Most recent link is old. Waiting for a new post...")
                            
                        first_run = False
                    else:
                        for link in links:
                            if link not in processed_links:
                                print(f"[*] New meeting link detected: {link}")
                                processed_links.add(link)
                                if check_if_recent(page_text, link):
                                    links_to_test.append(link)
                                else:
                                    print(f"[-] Ignored {link} as it violates constraints.")
                    
                    for link in links_to_test:
                        decoded_link = urllib.parse.unquote(link)
                        join_success = False
                        
                        if "meet.google.com" in decoded_link:
                            join_success = join_google_meet(driver, link)
                            platform = "meet"
                        elif "zoom.us" in decoded_link:
                            print(f"[!] Zoom Link found: {link}. Auto-join inside browser not fully implemented yet.")
                            join_success = False
                        elif "teams.microsoft.com" in decoded_link or "teams.live.com" in decoded_link:
                            join_success = join_teams_meeting(driver, link)
                            platform = "teams"
                            
                        if join_success:
                            print("Meeting joined. Watching until class ends...")
                            global AUTO_REPLIED
                            STOP_LISTENING = False
                            AUTO_REPLIED = False
                            audio_queue.queue.clear()
                            
                            t_sender = threading.Thread(target=network_sender_worker, args=(driver, platform), daemon=True)
                            t_sender.start()
                            
                            t_waiter = threading.Thread(target=recorder_worker, daemon=True)
                            t_waiter.start()
                            
                            while datetime.now().time() <= current_class["end_time"]:
                                time.sleep(5)
                                
                            STOP_LISTENING = True
                            class_ended_flag = True
                            print(f"\n[!] Class {current_class['subject']} has ended. Closing Chrome.")
                            break
                        else:
                            print("[-] Meeting join failed or unsupported. Returning to monitor stream...")
                                
                    if class_ended_flag:
                        break
                        
                    if not first_run and not links_to_test:
                        print(f"No new links found. Waiting {CHECK_INTERVAL_SECONDS} seconds until next check...")
                        
                    time.sleep(CHECK_INTERVAL_SECONDS)
                    
            finally:
                print("Closing browser for this class session...")
                try:
                    STOP_LISTENING = True
                    time.sleep(2) 
                    driver.quit()
                except:
                    pass
            
            print("Waiting for next class...")
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\n[+] Script stopped by user (Ctrl+C).")

if __name__ == "__main__":
    main()