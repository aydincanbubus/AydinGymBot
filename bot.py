import os
import json
import logging
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from io import BytesIO
import httpx

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_FILE = "data.json"
WEIGHT_FILE = "weights.json"
CHAT_HISTORY_FILE = "chat_history.json"

# ─── PROGRAM ──────────────────────────────────────────────────────────────────
PROGRAM = {
    "Salı": {
        "label": "💪 Omuz & Biceps & Forearm",
        "exercises": [
            "Dumbbell Omuz Aleti", "Overhead Barbell Press", "Dumbbell Shoulder Press",
            "Dumbbell Alternate Curl", "Barbell Curl", "Hammer Curl", "Bilek (Z Bar)",
        ],
        "tips": [
            "Omuz hareketlerinde rotator cuff'a dikkat — ısınmayı atlatma.",
            "Biceps için kontrollü negatif faz önemli.",
            "Bileği yavaş çalış, eklem sağlığı için kritik.",
        ]
    },
    "Perşembe": {
        "label": "🏋️ Göğüs & Triceps",
        "exercises": [
            "Chest Machine Press", "Incline Dumbbell Press", "Dumbbell Fly",
            "Cable Crossover (Üstten)", "Rope Pushdown", "Overhead Dumbbell Extension", "V Bar Pushdown",
        ],
        "tips": [
            "İzole hareketlerde ağırlık yerine sıkışmaya odaklan.",
            "Triceps için dirsek stabilitesini koru.",
        ]
    },
    "Cumartesi": {
        "label": "🦾 Sırt & Biceps",
        "exercises": [
            "V Bar Pulldown", "Hammer Strength Low Row", "Front Pulldown",
            "Dumbbell Alternate Curl", "Barbell Curl", "Hammer Curl",
        ],
        "tips": [
            "Sırt hareketlerinde skapula retraksiyon — her çekişte kürek kemiklerini sıkıştır.",
            "Biceps burada yorgunken form bozulmasın.",
        ]
    },
    "Pazar": {
        "label": "🔥 Omuz & Triceps",
        "exercises": [
            "Dumbbell Lateral Raise", "Rope Pulldown", "Shrug",
            "Overhead Triceps Press", "Rope Pushdown", "Düz Bar Pushdown", "Bilek (Z Bar)",
        ],
        "tips": [
            "Lateral Raise'de dirsekleri hafif bükük tut.",
            "Shrug'da boyun sıkışmasına dikkat.",
            "Bilek: dumbbell ile çalışmayı dene.",
        ]
    },
}

TRAINING_DAYS = {"Salı": 1, "Perşembe": 3, "Cumartesi": 5, "Pazar": 6}  # weekday() values
CHOOSE_DAY, CHOOSE_EXERCISE, ENTER_SETS, CHATBOT, ENTER_WEIGHT = range(5)

# ─── VERİ ─────────────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_weights():
    if os.path.exists(WEIGHT_FILE):
        with open(WEIGHT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_weights(w):
    with open(WEIGHT_FILE, "w", encoding="utf-8") as f:
        json.dump(w, f, ensure_ascii=False, indent=2)

def load_chat_history():
    if os.path.exists(CHAT_HISTORY_FILE):
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_chat_history(history):
    # Keep last 20 messages
    history = history[-20:]
    with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_today_str():
    return date.today().isoformat()

def get_today_gun():
    """Returns today's training day name if it's a training day, else None"""
    weekday = datetime.now().weekday()
    for gun, wd in TRAINING_DAYS.items():
        if weekday == wd:
            return gun
    return None

def calc_1rm(weight, reps):
    """Epley formula"""
    if reps == 1:
        return weight
    return weight * (1 + reps / 30.0)

def get_exercise_history(ex_name):
    """Get all entries for an exercise sorted by date"""
    data = load_data()
    history = []
    for date_str in sorted(data.keys()):
        for gun, gun_data in data[date_str].items():
            for ex, sets in gun_data.items():
                if ex.lower() == ex_name.lower():
                    max_w = max(s['agirlik'] for s in sets)
                    best_1rm = max(calc_1rm(s['agirlik'], s['tekrar']) for s in sets)
                    volume = sum(s['agirlik'] * s['tekrar'] for s in sets)
                    history.append({
                        "date": datetime.strptime(date_str, "%Y-%m-%d"),
                        "max_weight": max_w,
                        "best_1rm": best_1rm,
                        "volume": volume,
                        "sets": sets
                    })
    return history

def build_context_for_ai():
    """Build a comprehensive context string for the AI chatbot"""
    data = load_data()
    weights = load_weights()
    
    context = "Kullanıcı profili:\n"
    context += "- Tüp mide ameliyatı geçirdi (9 ay önce), 156kg'dan 85kg'a indi\n"
    context += "- Aktif spor yapıyor, haftada 4 gün antrenman\n\n"
    
    context += "Antrenman programı:\n"
    for gun, info in PROGRAM.items():
        context += f"- {gun}: {', '.join(info['exercises'])}\n"
    
    if weights:
        sorted_w = sorted(weights.items())
        context += f"\nVücut ağırlığı geçmişi (son 5):\n"
        for d, w in sorted_w[-5:]:
            context += f"- {d}: {w}kg\n"
    
    context += "\nSon antrenman verileri (maks ağırlıklar):\n"
    for date_str in sorted(data.keys())[-8:]:
        for gun, gun_data in data[date_str].items():
            context += f"{date_str} {gun}:\n"
            for ex, sets in gun_data.items():
                max_w = max(s['agirlik'] for s in sets)
                vol = sum(s['agirlik'] * s['tekrar'] for s in sets)
                context += f"  {ex}: maks {max_w}kg, hacim {vol:.0f}kg\n"
    
    # Stagnation check
    context += "\nDurağanlık analizi (3+ hafta aynı ağırlık):\n"
    all_exercises = set()
    for gun_info in PROGRAM.values():
        for ex in gun_info['exercises']:
            all_exercises.add(ex)
    
    for ex in all_exercises:
        history = get_exercise_history(ex)
        if len(history) >= 3:
            recent = history[-3:]
            weights_recent = [h['max_weight'] for h in recent]
            if max(weights_recent) == min(weights_recent):
                context += f"  - {ex}: {len(recent)} antrenman boyunca {weights_recent[0]}kg'da takılı\n"
    
    return context

# ─── HATIRLATICI ──────────────────────────────────────────────────────────────
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.data
    gun = get_today_gun()
    if gun:
        info = PROGRAM[gun]
        text = (
            f"🏋️ *Bugün {gun} günü!*\n"
            f"{info['label']}\n\n"
            f"📋 Hareketler:\n"
            + "\n".join([f"  {i+1}. {ex}" for i, ex in enumerate(info['exercises'])])
            + "\n\n/antrenman yazarak başla 💪"
        )
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")

async def hatirlatici_kur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Remove existing jobs
    current_jobs = context.job_queue.get_jobs_by_name(f"reminder_{user_id}")
    for job in current_jobs:
        job.schedule_removal()
    
    # Schedule daily at 12:00
    context.job_queue.run_daily(
        send_reminder,
        time=datetime.strptime("12:00", "%H:%M").time(),
        days=(1, 3, 5, 6),  # Tue, Thu, Sat, Sun
        data=user_id,
        name=f"reminder_{user_id}"
    )
    await update.message.reply_text(
        "✅ Hatırlatıcı kuruldu!\nHer antrenman günü saat 12:00'de mesaj atacağım.",
        parse_mode="Markdown"
    )

# ─── HAFTALIK RAPOR ──────────────────────────────────────────────────────────
async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.data
    report = generate_weekly_report_text()
    await context.bot.send_message(chat_id=user_id, text=report, parse_mode="Markdown")
    
    # Send volume chart
    buf = generate_weekly_volume_chart()
    if buf:
        await context.bot.send_photo(chat_id=user_id, photo=buf, caption="📊 Haftalık Hacim Trendi")

async def haftalik_rapor_kur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_jobs = context.job_queue.get_jobs_by_name(f"weekly_{user_id}")
    for job in current_jobs:
        job.schedule_removal()
    
    context.job_queue.run_daily(
        send_weekly_report,
        time=datetime.strptime("20:00", "%H:%M").time(),
        days=(6,),  # Sunday
        data=user_id,
        name=f"weekly_{user_id}"
    )
    
    # Also send now
    report = generate_weekly_report_text()
    await update.message.reply_text(report, parse_mode="Markdown")
    buf = generate_weekly_volume_chart()
    if buf:
        await update.message.reply_photo(photo=buf, caption="📊 Haftalık Hacim Trendi")

def generate_weekly_report_text():
    data = load_data()
    weights = load_weights()
    
    # Last 7 days
    today = date.today()
    week_ago = today - timedelta(days=7)
    
    report = "📊 *Haftalık Rapor*\n\n"
    
    sessions = 0
    total_volume = 0
    prs = []
    
    for date_str, day_data in data.items():
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        if d >= week_ago:
            sessions += 1
            for gun, gun_data in day_data.items():
                for ex, sets in gun_data.items():
                    vol = sum(s['agirlik'] * s['tekrar'] for s in sets)
                    total_volume += vol
                    
                    # Check PR
                    history = get_exercise_history(ex)
                    if history and len(history) >= 2:
                        current_max = max(s['agirlik'] for s in sets)
                        prev_max = max(h['max_weight'] for h in history[:-1])
                        if current_max > prev_max:
                            prs.append(f"{ex}: {prev_max}kg → {current_max}kg")
    
    report += f"🏋️ Antrenman sayısı: *{sessions}*\n"
    report += f"💥 Toplam hacim: *{total_volume:.0f}kg*\n"
    
    if prs:
        report += f"\n🏆 *Bu hafta kırdığın rekorlar:*\n"
        for pr in prs:
            report += f"  ✅ {pr}\n"
    
    if weights:
        sorted_w = sorted(weights.items())
        if len(sorted_w) >= 2:
            diff = sorted_w[-1][1] - sorted_w[-2][1]
            sign = "+" if diff > 0 else ""
            report += f"\n⚖️ Vücut ağırlığı: *{sorted_w[-1][1]}kg* ({sign}{diff:.1f}kg)\n"
    
    # Stagnation warnings
    stagnant = []
    all_exercises = set()
    for gun_info in PROGRAM.values():
        for ex in gun_info['exercises']:
            all_exercises.add(ex)
    
    for ex in all_exercises:
        history = get_exercise_history(ex)
        if len(history) >= 3:
            recent = [h['max_weight'] for h in history[-3:]]
            if max(recent) == min(recent):
                stagnant.append(f"{ex} ({recent[0]}kg, {len(history[-3:])} idman)")
    
    if stagnant:
        report += f"\n⚠️ *Durağan hareketler (öneri için /koç yaz):*\n"
        for s in stagnant:
            report += f"  • {s}\n"
    
    return report

# ─── GRAFİKLER ────────────────────────────────────────────────────────────────
def generate_weekly_volume_chart():
    data = load_data()
    if not data:
        return None
    
    # Group by week
    weekly = {}
    for date_str, day_data in data.items():
        d = datetime.strptime(date_str, "%Y-%m-%d")
        week_start = d - timedelta(days=d.weekday())
        week_key = week_start.strftime("%Y-%m-%d")
        if week_key not in weekly:
            weekly[week_key] = 0
        for gun, gun_data in day_data.items():
            for ex, sets in gun_data.items():
                weekly[week_key] += sum(s['agirlik'] * s['tekrar'] for s in sets)
    
    if len(weekly) < 1:
        return None
    
    dates = [datetime.strptime(k, "%Y-%m-%d") for k in sorted(weekly.keys())]
    volumes = [weekly[k] for k in sorted(weekly.keys())]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')
    
    ax.bar(dates, volumes, color='#e94560', edgecolor='#ff6b8a', linewidth=0.8, width=5)
    if len(dates) >= 2:
        x_num = mdates.date2num(dates)
        z = np.polyfit(x_num, volumes, 1)
        p = np.poly1d(z)
        ax.plot(dates, p(x_num), '--', color='#f5a623', linewidth=2, label='Trend')
        ax.legend(facecolor='#16213e', edgecolor='#444', labelcolor='white')
    
    ax.set_title('📈 Haftalık Toplam Hacim Trendi', color='white', fontsize=14, fontweight='bold')
    ax.set_ylabel('Toplam Hacim (kg)', color='white')
    ax.tick_params(colors='white')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, color='#aaaaaa')
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    for spine in ['bottom', 'left']:
        ax.spines[spine].set_color('#444')
    
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close()
    return buf

def generate_day_chart(gun, today, data):
    gun_data = data.get(today, {}).get(gun, {})
    if not gun_data:
        return None
    
    exercises = list(gun_data.keys())
    max_weights = [max(s['agirlik'] for s in sets) for sets in gun_data.values()]
    volumes = [sum(s['agirlik'] * s['tekrar'] for s in sets) for sets in gun_data.values()]
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.patch.set_facecolor('#1a1a2e')
    colors = plt.cm.plasma(np.linspace(0.3, 0.9, len(exercises)))
    short_names = [ex[:18] + '..' if len(ex) > 18 else ex for ex in exercises]
    
    for ax, vals, title in [(ax1, max_weights, '💪 Maks Ağırlık (kg)'), (ax2, volumes, '📊 Toplam Hacim (kg)')]:
        bars = ax.bar(range(len(exercises)), vals, color=colors, edgecolor='white', linewidth=0.5)
        ax.set_facecolor('#16213e')
        ax.set_title(title, color='white', fontsize=13, fontweight='bold', pad=10)
        ax.set_xticks(range(len(exercises)))
        ax.set_xticklabels(short_names, rotation=45, ha='right', color='#aaaaaa', fontsize=8)
        ax.set_ylabel('kg', color='white')
        ax.tick_params(colors='white')
        for sp in ['top', 'right']:
            ax.spines[sp].set_visible(False)
        for sp in ['bottom', 'left']:
            ax.spines[sp].set_color('#444')
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.5,
                   f'{val:.0f}', ha='center', va='bottom', color='white', fontsize=9, fontweight='bold')
    
    fig.suptitle(f'{gun} — {today}', color='white', fontsize=15, fontweight='bold')
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close()
    return buf

def generate_progress_chart(exercise_name):
    history = get_exercise_history(exercise_name)
    if len(history) < 2:
        return None, "Grafik için en az 2 kayıt gerekli."
    
    dates = [h['date'] for h in history]
    max_weights = [h['max_weight'] for h in history]
    one_rms = [h['best_1rm'] for h in history]
    volumes = [h['volume'] for h in history]
    
    fig, axes = plt.subplots(3, 1, figsize=(12, 12))
    fig.patch.set_facecolor('#1a1a2e')
    
    configs = [
        (axes[0], max_weights, '#e94560', '💪 Maks Ağırlık (kg)'),
        (axes[1], one_rms, '#f5a623', '🏆 Tahmini 1RM (kg)'),
        (axes[2], volumes, '#4ecdc4', '📊 Toplam Hacim (kg)'),
    ]
    
    for ax, vals, color, title in configs:
        ax.plot(dates, vals, 'o-', color=color, linewidth=2.5, markersize=7, markerfacecolor='white')
        ax.fill_between(dates, vals, alpha=0.15, color=color)
        ax.set_facecolor('#16213e')
        ax.set_title(title, color='white', fontsize=13, fontweight='bold')
        ax.set_ylabel('kg', color='white')
        ax.tick_params(colors='white')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, color='#aaaaaa')
        for sp in ['top', 'right']:
            ax.spines[sp].set_visible(False)
        for sp in ['bottom', 'left']:
            ax.spines[sp].set_color('#444')
        if len(dates) >= 3:
            x_num = mdates.date2num(dates)
            z = np.polyfit(x_num, vals, 1)
            p = np.poly1d(z)
            ax.plot(dates, p(x_num), '--', color='white', linewidth=1, alpha=0.4, label='Trend')
            ax.legend(facecolor='#16213e', edgecolor='#444', labelcolor='white', fontsize=8)
        
        # Mark PRs
        max_val = max(vals)
        max_idx = vals.index(max_val)
        ax.annotate(f'PR: {max_val:.1f}kg', xy=(dates[max_idx], max_val),
                   xytext=(10, 10), textcoords='offset points',
                   color='gold', fontsize=9, fontweight='bold',
                   arrowprops=dict(arrowstyle='->', color='gold', lw=1.5))
    
    fig.suptitle(f'{exercise_name} — Güç Gelişimi', color='white', fontsize=15, fontweight='bold')
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close()
    return buf, None

# ─── VÜCUT AĞIRLIĞI ──────────────────────────────────────────────────────────
async def agirlik_gir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚖️ Bugünkü vücut ağırlığını gir (kg):\nÖrnek: `87.5`",
        parse_mode="Markdown"
    )
    return ENTER_WEIGHT

async def agirlik_kaydet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        w = float(update.message.text.replace(',', '.'))
    except:
        await update.message.reply_text("⚠️ Sayı gir, örnek: `87.5`", parse_mode="Markdown")
        return ENTER_WEIGHT
    
    weights = load_weights()
    today = get_today_str()
    weights[today] = w
    save_weights(weights)
    
    msg = f"✅ *{w}kg* kaydedildi!\n\n"
    
    sorted_w = sorted(weights.items())
    if len(sorted_w) >= 2:
        diff = sorted_w[-1][1] - sorted_w[-2][1]
        sign = "+" if diff > 0 else ""
        msg += f"Önceki: {sorted_w[-2][1]}kg → Şimdi: {w}kg ({sign}{diff:.1f}kg)\n"
    
    if len(sorted_w) >= 2:
        first_w = sorted_w[0][1]
        total_diff = w - first_w
        msg += f"Başlangıçtan beri: {total_diff:+.1f}kg"
    
    await update.message.reply_text(msg, parse_mode="Markdown")
    
    # Send weight chart if enough data
    if len(sorted_w) >= 3:
        buf = generate_weight_chart(weights)
        if buf:
            await update.message.reply_photo(photo=buf, caption="📈 Vücut Ağırlığı Grafiği")
    
    return ConversationHandler.END

def generate_weight_chart(weights):
    sorted_w = sorted(weights.items())
    if len(sorted_w) < 2:
        return None
    
    dates = [datetime.strptime(k, "%Y-%m-%d") for k, _ in sorted_w]
    vals = [v for _, v in sorted_w]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')
    ax.plot(dates, vals, 'o-', color='#4ecdc4', linewidth=2.5, markersize=8, markerfacecolor='white')
    ax.fill_between(dates, vals, alpha=0.2, color='#4ecdc4')
    
    if len(dates) >= 3:
        x_num = mdates.date2num(dates)
        z = np.polyfit(x_num, vals, 1)
        p = np.poly1d(z)
        ax.plot(dates, p(x_num), '--', color='#f5a623', linewidth=1.5, label='Trend')
        ax.legend(facecolor='#16213e', edgecolor='#444', labelcolor='white')
    
    ax.set_title('⚖️ Vücut Ağırlığı Takibi', color='white', fontsize=14, fontweight='bold')
    ax.set_ylabel('kg', color='white')
    ax.tick_params(colors='white')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, color='#aaaaaa')
    for sp in ['top', 'right']:
        ax.spines[sp].set_visible(False)
    for sp in ['bottom', 'left']:
        ax.spines[sp].set_color('#444')
    
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close()
    return buf

# ─── KOÇ / CHATBOT ───────────────────────────────────────────────────────────
async def koc_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Koç modu aktif!*\n\n"
        "Antrenman, beslenme, güç gelişimi hakkında soru sorabilirsin.\n"
        "Verilerini analiz edip sana özel öneriler vereceğim.\n\n"
        "Çıkmak için /bitti yaz.",
        parse_mode="Markdown"
    )
    return CHATBOT

async def koc_cevap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    
    if not GEMINI_API_KEY:
        await update.message.reply_text(
            "⚠️ AI bağlantısı için GEMINI_API_KEY gerekli.\n"
            "Railway'de bu environment variable'ı ekle."
        )
        return CHATBOT
    
    await update.message.reply_text("⏳ Düşünüyorum...")
    
    history = load_chat_history()
    context_str = build_context_for_ai()
    
    system_prompt = f"""Sen bir kişisel fitness koçusun. Kullanıcı hakkında şu bilgilere sahipsin:

{context_str}

Önemli notlar:
- Kullanıcı tüp mide ameliyatı geçirdi, protein emilimi ve beslenme önerileri buna göre olmalı
- Türkçe konuş, samimi ve motive edici ol
- Verilerini analiz et, somut öneriler ver
- Eğer bir harekette durağanlık varsa beslenme (özellikle protein) ve antrenman düzeni öner
- 1RM hesaplamalarını kullan
- Uzun cevaplar verme, net ve actionable ol"""

    # Build Gemini contents (system + history + new message)
    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_msg}]})

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": contents,
                    "generationConfig": {"maxOutputTokens": 1000}
                }
            )
            result = resp.json()
            ai_reply = result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"AI error: {e}")
        ai_reply = "⚠️ Bağlantı hatası, tekrar dene."
    
    # Save history
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": ai_reply})
    save_chat_history(history)
    
    await update.message.reply_text(ai_reply, parse_mode="Markdown")
    return CHATBOT

async def koc_bitti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Koç modu kapatıldı. Antrenmanlarında başarılar!")
    return ConversationHandler.END

# ─── ANTRENMaN ────────────────────────────────────────────────────────────────
async def antrenman_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_gun = get_today_gun()
    keyboard = []
    for gun in PROGRAM.keys():
        emoji = "✅ " if gun == today_gun else ""
        keyboard.append([InlineKeyboardButton(f"{emoji}{gun} — {PROGRAM[gun]['label']}", callback_data=f"gun_{gun}")])
    
    if today_gun:
        text = f"🗓 Bugün *{today_gun}* günü! Otomatik seçildi ya da başka gün seçebilirsin:"
    else:
        text = "🗓 *Hangi günün antrenmanını giriyorsun?*"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    return CHOOSE_DAY

async def gun_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gun = query.data.replace("gun_", "")
    context.user_data['gun'] = gun
    return await goster_egzersizler(query, context, gun)

async def goster_egzersizler(query_or_msg, context, gun):
    data = load_data()
    today = get_today_str()
    exercises = PROGRAM[gun]['exercises']
    keyboard = []
    for i, ex in enumerate(exercises):
        done = ""
        if today in data and gun in data[today] and ex in data[today][gun]:
            done = "✅ "
        keyboard.append([InlineKeyboardButton(f"{done}{i+1}. {ex}", callback_data=f"ex_{i}")])
    keyboard.append([InlineKeyboardButton("🏁 Bitti, grafik göster", callback_data="ex_done")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"*{gun} — {PROGRAM[gun]['label']}*\n\nHangi hareketi girmek istiyorsun?"
    
    if hasattr(query_or_msg, 'edit_message_text'):
        await query_or_msg.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await query_or_msg.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    return CHOOSE_EXERCISE

async def egzersiz_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "ex_done":
        return await gunu_bitir(update, context)
    
    ex_idx = int(query.data.replace("ex_", ""))
    gun = context.user_data['gun']
    ex_name = PROGRAM[gun]['exercises'][ex_idx]
    context.user_data['exercise'] = ex_name
    
    # Show previous data if exists
    history = get_exercise_history(ex_name)
    prev_text = ""
    if history:
        last = history[-1]
        sets_str = " | ".join([f"{s['agirlik']}x{s['tekrar']}" for s in last['sets']])
        prev_text = f"\n📋 Son kayıt ({last['date'].strftime('%d/%m')}): {sets_str}"
    
    await query.edit_message_text(
        f"💪 *{ex_name}*{prev_text}\n\n"
        f"Set verilerini gir: `ağırlık x tekrar` boşlukla ayır\n"
        f"Örnek: `50x10 60x8 70x5`",
        parse_mode="Markdown"
    )
    return ENTER_SETS

async def set_gir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    gun = context.user_data['gun']
    ex_name = context.user_data['exercise']
    
    sets = []
    try:
        for part in text.split():
            if 'x' in part.lower():
                w, r = part.lower().split('x')
                sets.append({"agirlik": float(w), "tekrar": int(r)})
        if not sets:
            raise ValueError()
    except:
        await update.message.reply_text("⚠️ Format: `50x10 60x8 70x5`", parse_mode="Markdown")
        return ENTER_SETS
    
    data = load_data()
    today = get_today_str()
    if today not in data:
        data[today] = {}
    if gun not in data[today]:
        data[today][gun] = {}
    data[today][gun][ex_name] = sets
    save_data(data)
    
    max_w = max(s['agirlik'] for s in sets)
    total_vol = sum(s['agirlik'] * s['tekrar'] for s in sets)
    best_1rm = max(calc_1rm(s['agirlik'], s['tekrar']) for s in sets)
    
    # Check PR
    history = get_exercise_history(ex_name)
    pr_text = ""
    if len(history) >= 2:
        prev_max = max(h['max_weight'] for h in history[:-1])
        if max_w > prev_max:
            pr_text = f"\n🏆 *YENİ REK OR! {prev_max}kg → {max_w}kg* 🎉"
    
    sets_text = " | ".join([f"{s['agirlik']}kg x{s['tekrar']}" for s in sets])
    
    exercises = PROGRAM[gun]['exercises']
    keyboard = []
    for i, ex in enumerate(exercises):
        done = "✅ " if (today in data and gun in data[today] and ex in data[today][gun]) else ""
        keyboard.append([InlineKeyboardButton(f"{done}{i+1}. {ex}", callback_data=f"ex_{i}")])
    keyboard.append([InlineKeyboardButton("🏁 Bitti, grafik göster", callback_data="ex_done")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ *{ex_name}* kaydedildi!\n"
        f"📊 {sets_text}\n"
        f"🏋️ Maks: {max_w}kg | 1RM: {best_1rm:.1f}kg | Hacim: {total_vol:.0f}kg"
        f"{pr_text}\n\nBaşka hareket?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return CHOOSE_EXERCISE

async def gunu_bitir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    gun = context.user_data.get('gun')
    today = get_today_str()
    data = load_data()
    
    if today not in data or gun not in data.get(today, {}):
        await query.edit_message_text("⚠️ Bugün için veri bulunamadı.")
        return ConversationHandler.END
    
    gun_data = data[today][gun]
    tips = PROGRAM[gun].get('tips', [])
    
    summary = f"🏁 *{gun} Antrenmanı Tamamlandı!*\n\n"
    for ex, sets in gun_data.items():
        max_w = max(s['agirlik'] for s in sets)
        vol = sum(s['agirlik'] * s['tekrar'] for s in sets)
        best_1rm = max(calc_1rm(s['agirlik'], s['tekrar']) for s in sets)
        summary += f"*{ex}*: {max_w}kg | 1RM ~{best_1rm:.1f}kg | Hacim {vol:.0f}kg\n"
    
    if tips:
        summary += "\n📌 *Notlar:*\n" + "\n".join([f"💡 {t}" for t in tips])
    
    await query.edit_message_text(summary, parse_mode="Markdown")
    buf = generate_day_chart(gun, today, data)
    if buf:
        await query.message.reply_photo(photo=buf, caption=f"📈 {gun} — Bugünkü performans")
    
    return ConversationHandler.END

async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ İptal edildi.")
    return ConversationHandler.END

# ─── DİĞER KOMUTLAR ───────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Auto-setup reminders
    current_jobs = context.job_queue.get_jobs_by_name(f"reminder_{user_id}")
    if not current_jobs:
        context.job_queue.run_daily(
            send_reminder,
            time=datetime.strptime("12:00", "%H:%M").time(),
            days=(1, 3, 5, 6),
            data=user_id,
            name=f"reminder_{user_id}"
        )
        context.job_queue.run_daily(
            send_weekly_report,
            time=datetime.strptime("20:00", "%H:%M").time(),
            days=(6,),
            data=user_id,
            name=f"weekly_{user_id}"
        )
    
    text = (
        "🏆 *Gym Tracker Bot'una hoş geldin!*\n\n"
        "📋 *Komutlar:*\n"
        "/antrenman — Antrenman ver gir\n"
        "/grafik — Hareket güç grafikleri\n"
        "/ozet — Haftalık özet\n"
        "/kilo — Vücut ağırlığı gir\n"
        "/koc — AI koçunla konuş\n"
        "/program — Haftalık program\n"
        "/hatirlatici — Hatırlatıcıyı kur\n\n"
        "⏰ Hatırlatıcı otomatik kuruldu (saat 12:00)\n"
        "📊 Haftalık rapor her Pazar 20:00'de gelecek"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def program_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📅 *Haftalık Programın:*\n\n"
    for gun, info in PROGRAM.items():
        text += f"*{gun}* — {info['label']}\n"
        for i, ex in enumerate(info['exercises'], 1):
            text += f"  {i}. {ex}\n"
        text += "\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def ozet_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = generate_weekly_report_text()
    await update.message.reply_text(report, parse_mode="Markdown")
    buf = generate_weekly_volume_chart()
    if buf:
        await update.message.reply_photo(photo=buf, caption="📊 Hacim Trendi")

async def grafik_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_exercises = []
    for gun_info in PROGRAM.values():
        for ex in gun_info['exercises']:
            if ex not in all_exercises:
                all_exercises.append(ex)
    
    keyboard = []
    row = []
    for i, ex in enumerate(all_exercises):
        row.append(InlineKeyboardButton(ex[:22], callback_data=f"graf_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    context.user_data['all_exercises'] = all_exercises
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📈 *Hangi hareketin grafiğini görmek istiyorsun?*", reply_markup=reply_markup, parse_mode="Markdown")

async def grafik_ciz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.replace("graf_", ""))
    all_exercises = context.user_data.get('all_exercises', [])
    if idx >= len(all_exercises):
        await query.edit_message_text("⚠️ Hata, tekrar dene.")
        return
    ex_name = all_exercises[idx]
    await query.edit_message_text(f"⏳ {ex_name} grafiği hazırlanıyor...")
    buf, error = generate_progress_chart(ex_name)
    if error:
        await query.message.reply_text(f"ℹ️ *{ex_name}*: {error}", parse_mode="Markdown")
    else:
        await query.message.reply_photo(photo=buf, caption=f"📈 {ex_name} — Güç Gelişimi (Maks / 1RM / Hacim)")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    
    antrenman_conv = ConversationHandler(
        entry_points=[CommandHandler("antrenman", antrenman_baslat)],
        states={
            CHOOSE_DAY: [CallbackQueryHandler(gun_sec, pattern="^gun_")],
            CHOOSE_EXERCISE: [CallbackQueryHandler(egzersiz_sec, pattern="^ex_")],
            ENTER_SETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_gir)],
        },
        fallbacks=[CommandHandler("iptal", iptal)],
    )
    
    koc_conv = ConversationHandler(
        entry_points=[CommandHandler("koc", koc_baslat)],
        states={CHATBOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, koc_cevap)]},
        fallbacks=[CommandHandler("bitti", koc_bitti)],
    )
    
    kilo_conv = ConversationHandler(
        entry_points=[CommandHandler("kilo", agirlik_gir)],
        states={ENTER_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, agirlik_kaydet)]},
        fallbacks=[CommandHandler("iptal", iptal)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("program", program_goster))
    app.add_handler(CommandHandler("ozet", ozet_goster))
    app.add_handler(CommandHandler("grafik", grafik_goster))
    app.add_handler(CommandHandler("hatirlatici", hatirlatici_kur))
    app.add_handler(CommandHandler("haftalikrapor", haftalik_rapor_kur))
    app.add_handler(CallbackQueryHandler(grafik_ciz, pattern="^graf_"))
    app.add_handler(antrenman_conv)
    app.add_handler(koc_conv)
    app.add_handler(kilo_conv)
    
    logger.info("Bot başlatıldı!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
