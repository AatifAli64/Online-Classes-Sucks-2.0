# 🎓 Online Classes Sucks — Auto Joiner Bot

A bot that automatically monitors your Google Classroom, detects new meeting links (Google Meet / Microsoft Teams), joins the class, records speaker audio, and streams it to a GPU-powered Kaggle server for real-time transcription. If your name is called, it auto-replies in chat.

---

## 🗂️ Project Structure

```
📁 Online-Classes-Sucks-2.0/
├── transcribed_online_class.py   # Main bot — runs on YOUR PC
├── kaggle_server.py              # Transcription server — runs on Kaggle (GPU)
├── requirements.txt              # Local dependencies
├── requirements_kaggle.txt       # Kaggle dependencies (for reference)
├── .env.example                  # Template showing what goes in .env
└── .gitignore                    # Keeps
```

---

## ⚙️ How It Works

```
Your PC                          Kaggle (Free GPU)
─────────────────────────────    ──────────────────────────
Chrome (Selenium)                FastAPI server
  → Opens Google Classroom       ← Receives audio chunks
  → Detects meeting link         → Transcribes with Whisper
  → Joins Meet / Teams           → Returns text + name detection
  → Records speaker audio   ──►  ──────────────────────────
  → If name detected, auto-replies in chat
```

---

## 🚀 PART 1 — One-Time Setup (Do This First!)

### Step 1: Clone the Repository

```bash
git clone https://github.com/AatifAli64/Online-Classes-Sucks-2.0.git
cd Online-Classes-Sucks-2.0
```

### Step 2: Install Local Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Create Your `.env` File

Copy the example file and fill in your values:

```bash
copy .env.example .env
```

Then open `.env` and fill in all the fields (see the section below for details).

---

## 🔑 PART 2 — Setting Up Your `.env` File

Open `.env` in any text editor and fill in the following:

### 1. Chrome Profile Path

You need to point the bot to your existing Chrome profile so it uses your logged-in Google account. This way it can access Google Classroom without typing a password.

**How to find your Chrome profile path:**
1. Open Chrome
2. Go to the address bar and type: `chrome://version`
3. Press Enter
4. Look for **"Profile Path"** — copy everything up to (but NOT including) the last folder name

**Example:**
```
Profile Path shown: C:\Users\YourName\AppData\Local\Google\Chrome\User Data\Profile 1

So set:
CHROME_PROFILE_PATH="C:\Users\YourName\AppData\Local\Google\Chrome\User Data"
PROFILE_DIRECTORY="Profile 1"
```

```env
CHROME_PROFILE_PATH="C:\Users\YourName\AppData\Local\Google\Chrome\User Data"
PROFILE_DIRECTORY="Profile 1"
```

> ⚠️ **Important:** Close ALL Chrome windows before running the bot. Chrome only allows one process per profile at a time.

### 2. Guest Name (for Teams)

This is the name shown when joining a Microsoft Teams meeting as a guest:

```env
GUEST_NAME="Your Full Name"
```

### 3. Google Classroom Links

For each subject, go to Google Classroom, open the **Stream** tab, and copy the URL from your browser:

```env
GCR_DF="https://classroom.google.com/u/0/c/YOUR_CLASS_ID"
GCR_INFO_SEC="https://classroom.google.com/u/0/c/YOUR_CLASS_ID"
# ... add all your subjects
```

### 4. Timetable (JSON)

Fill in your weekly class schedule. Use `HH:MM` (24-hour format). The `env_link` must exactly match one of your `GCR_` variable names above:

```env
TIMETABLE='{"Monday": [{"subject": "DF", "start": "08:30", "end": "09:50", "env_link": "GCR_DF"}, {"subject": "Info-Sec", "start": "10:00", "end": "11:20", "env_link": "GCR_INFO_SEC"}], "Tuesday": [...]}'
```

### 5. Kaggle Server URL (fill this in later — see Part 3)

```env
KAGGLE_SERVER_URL="https://your-ngrok-url.ngrok-free.app"
```

---

## 🔐 PART 3 — First-Time Chrome Login (Very Important!)

The bot uses your Chrome profile so it stays logged in. But **the first time you run it**, you need to log in manually to cache your session.

1. Open Chrome normally (not through the bot)
2. Log into your **Google account** (the one with Google Classroom access)
3. Visit [https://classroom.google.com](https://classroom.google.com) and make sure you can see your classes
4. Close Chrome completely

That's it! From now on, the bot will use your saved session automatically — no login needed again.

---

## 🖥️ PART 4 — Setting Up the Kaggle Server (GPU Transcription)

The heavy transcription work runs on Kaggle's free T4 GPUs. Here's how to set it up:

### Step 1: Create a Free Kaggle Account

Go to [https://www.kaggle.com](https://www.kaggle.com) and sign up.

### Step 2: Get Your ngrok Auth Token

ngrok creates a public URL tunnel to your Kaggle server so your PC can talk to it.

1. Go to [https://dashboard.ngrok.com/signup](https://dashboard.ngrok.com/signup) and sign up for free
2. After logging in, go to **"Your Authtoken"** in the left sidebar: [https://dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken)
3. Copy your auth token — it looks like: `2abc123XYZ_abcdefghijklmnop`

### Step 3: Add Your ngrok Token to `kaggle_server.py`

Open `kaggle_server.py` and find this line near the bottom:

```python
NGROK_AUTH_TOKEN = "ngrok authtoken token here"
```

Replace it with your actual token:

```python
NGROK_AUTH_TOKEN = "2abc123XYZ_abcdefghijklmnop"   # ← paste your token here
```

### Step 4: Create a New Kaggle Notebook

1. Go to [https://www.kaggle.com/code](https://www.kaggle.com/code)
2. Click **"New Notebook"**
3. On the right side panel → **Settings** → Set **Accelerator** to **"GPU T4 x2"**
4. Make sure **"Internet"** is turned **ON** (required for ngrok)

### Step 5: Paste the Server Code

1. Delete the default code in the notebook
2. In the **first cell**, paste everything from `kaggle_server.py`
3. The first line in the file is the install command — it installs all dependencies automatically:
   ```python
   !pip install -q fastapi uvicorn pyngrok soundfile python-multipart faster-whisper torch nest_asyncio librosa
   ```
4. Click **"Run All"** (▶▶) or press `Shift+Enter` on each cell

> ⏳ First run takes 3–5 minutes to download the Whisper model. Be patient.

### Step 6: Copy the ngrok URL

Once the server starts, you'll see output like this in the notebook:

```
================================================================================
NGROK URL IS: https://abc123-random.ngrok-free.app
================================================================================
```

Copy that URL.

### Step 7: Paste the URL into Your `.env`

Open your local `.env` file and set:

```env
KAGGLE_SERVER_URL="https://abc123-random.ngrok-free.app"
```

> ⚠️ This URL **changes every time** you restart the Kaggle session. You must update `.env` each time you start a new Kaggle session.

---

## ▶️ PART 5 — Running the Bot Locally

Once your `.env` is filled in and the Kaggle server is running:

```bash
python transcribed_online_class.py
```

The bot will:
1. Check your timetable for the current class
2. Open Chrome and navigate to Google Classroom
3. Detect any new meeting links posted by the teacher
4. Automatically join the meeting (Google Meet or Teams)
5. Start recording speaker audio and streaming to Kaggle
6. Print live transcription in your terminal
7. Auto-reply in chat if your name is detected

To stop the bot at any time:
```bash
Ctrl + C
```

---

## 📋 Quick Reference — Run Order Checklist

Every time you want to use the bot:

```
[ ] 1. Start Kaggle notebook → Run All → Wait for "NGROK URL IS:" message
[ ] 2. Copy the ngrok URL → Paste into .env → KAGGLE_SERVER_URL="..."
[ ] 3. Close all Chrome windows
[ ] 4. Run: python transcribed_online_class.py
[ ] 5. Bot joins class automatically at scheduled time ✅
```

---

## ❓ Troubleshooting

| Problem | Fix |
|---|---|
| `Chrome failed to start` | Make sure ALL Chrome windows are fully closed |
| `Could not connect to ngrok URL` | Kaggle session may have expired — restart notebook |
| `No class currently active` | Check that your timetable in `.env` is correct and time is right |
| `Guest name input not found` | Teams loaded slowly — try increasing the `time.sleep(25)` in the code |
| Bot joins but no transcription | Check that the ngrok URL in `.env` matches the current Kaggle session |

---

## 🔒 Security Notes


- The ngrok URL is a random unguessable string that changes every session ✅
- Your Chrome login credentials are never stored in the code ✅
