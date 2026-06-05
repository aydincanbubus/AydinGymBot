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
CHOOSE_DAY, CHOOSE_EXERCISE, ENTER_SET, CHATBOT, ENTER_WEIGHT = range(5)
ENTER_HEIGHT, ENTER_NECK, ENTER_WAIST = range(5, 8)

PROFILE_FILE = "profile.json"

def load_profile():
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_profile(p):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)

def calc_body_fat_navy(weight_kg, height_cm, neck_cm, waist_cm):
    """US Navy body fat formula for males"""
    import math
    height_in = height_cm / 2.54
    neck_in = neck_cm / 2.54
    waist_in = waist_cm / 2.54
    bf = 86.010 * math.log10(waist_in - neck_in) - 70.041 * math.log10(height_in) + 36.76
    return round(bf, 1)

def calc_bmi(weight_kg, height_cm):
    h = height_cm / 100
    return round(weight_kg / (h * h), 1)

def bmi_category(bmi):
    if bmi < 18.5: return "Zayıf"
    elif bmi < 25: return "Normal"
    elif bmi < 30: return "Fazla kilolu"
    elif bmi < 35: return "Obez (Sınıf 1)"
    elif bmi < 40: return "Obez (Sınıf 2)"
    else: return "Morbid obez"

def ideal_weight_range(height_cm):
    h = height_cm / 100
    low = round(18.5 * h * h, 1)
    high = round(24.9 * h * h, 1)
    return low, high

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

# ─── YAĞ ORANI & BMI ─────────────────────────────────────────────────────────
async def vucut_analiz_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_profile()
    if profile.get('height_cm'):
        await update.message.reply_text(
            f"📏 Kayıtlı boyun: *{profile['height_cm']}cm*\n"
            f"Boyunu değiştirmek için yeni değer gir, aynı kalması için /atla yaz:",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "📏 *Vücut Analizi*\n\nBoyunu gir (cm):\nÖrnek: `178`",
            parse_mode="Markdown"
        )
    return ENTER_HEIGHT

async def boy_gir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() == '/atla':
        profile = load_profile()
        context.user_data['height_cm'] = profile.get('height_cm', 175)
    else:
        try:
            h = float(update.message.text.replace(',', '.'))
            if not (100 < h < 250):
                raise ValueError()
            context.user_data['height_cm'] = h
            profile = load_profile()
            profile['height_cm'] = h
            save_profile(profile)
        except:
            await update.message.reply_text("⚠️ Geçerli bir boy gir (cm), örnek: `178`", parse_mode="Markdown")
            return ENTER_HEIGHT

    await update.message.reply_text(
        "📏 Boyun çevresini gir (cm) — çenenin hemen altından ölç:\nÖrnek: `38`",
        parse_mode="Markdown"
    )
    return ENTER_NECK

async def boyun_gir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = float(update.message.text.replace(',', '.'))
        if not (20 < n < 70):
            raise ValueError()
        context.user_data['neck_cm'] = n
    except:
        await update.message.reply_text("⚠️ Geçerli bir değer gir, örnek: `38`", parse_mode="Markdown")
        return ENTER_NECK

    await update.message.reply_text(
        "📏 Bel çevresini gir (cm) — göbek deliği hizasından ölç:\nÖrnek: `92`",
        parse_mode="Markdown"
    )
    return ENTER_WAIST

async def bel_gir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        w = float(update.message.text.replace(',', '.'))
        if not (40 < w < 200):
            raise ValueError()
    except:
        await update.message.reply_text("⚠️ Geçerli bir değer gir, örnek: `92`", parse_mode="Markdown")
        return ENTER_WAIST

    height = context.user_data['height_cm']
    neck = context.user_data['neck_cm']
    waist = w

    # Load current weight
    weights = load_weights()
    sorted_w = sorted(weights.items())
    current_weight = sorted_w[-1][1] if sorted_w else None

    # Calculations
    bf = calc_body_fat_navy(current_weight or 85, height, neck, waist)
    bmi = calc_bmi(current_weight or 85, height) if current_weight else None
    ideal_low, ideal_high = ideal_weight_range(height)

    # Save measurements
    profile = load_profile()
    profile['last_neck'] = neck
    profile['last_waist'] = waist
    measurements = profile.get('measurements', [])
    measurements.append({
        "date": get_today_str(),
        "neck": neck,
        "waist": waist,
        "body_fat": bf,
        "weight": current_weight
    })
    profile['measurements'] = measurements
    save_profile(profile)

    # Body fat category
    if bf < 6: bf_cat = "Esansiyel yağ (çok düşük)"
    elif bf < 14: bf_cat = "Sporcu"
    elif bf < 18: bf_cat = "Fit"
    elif bf < 25: bf_cat = "Normal"
    elif bf < 32: bf_cat = "Fazla"
    else: bf_cat = "Obez"

    msg = f"📊 *Vücut Analizi Sonuçları*\n\n"
    msg += f"📏 Boy: {height}cm | Boyun: {neck}cm | Bel: {waist}cm\n\n"
    msg += f"🔥 *Yağ Oranı: %{bf}* — {bf_cat}\n"

    if current_weight:
        fat_kg = round(current_weight * bf / 100, 1)
        lean_kg = round(current_weight - fat_kg, 1)
        msg += f"   Yağ kütlesi: {fat_kg}kg | Yağsız kütle: {lean_kg}kg\n\n"
        if bmi:
            msg += f"⚖️ *BMI: {bmi}* — {bmi_category(bmi)}\n"
            msg += f"   İdeal kilo aralığı: {ideal_low}–{ideal_high}kg\n"
            diff = round(current_weight - ideal_high, 1)
            if diff > 0:
                msg += f"   İdeal aralığa ulaşmak için: -{diff}kg\n"
            else:
                msg += f"   ✅ İdeal kilo aralığındasın!\n"
    else:
        msg += f"\n⚠️ Kilo kaydın yok, /kilo ile ekle (daha doğru sonuç için)\n"

    if len(measurements) >= 2:
        prev = measurements[-2]
        bf_diff = round(bf - prev['body_fat'], 1)
        waist_diff = round(waist - prev['waist'], 1)
        sign_bf = "+" if bf_diff > 0 else ""
        sign_w = "+" if waist_diff > 0 else ""
        msg += f"\n📈 Önceki ölçüme göre:\n"
        msg += f"   Yağ oranı: {sign_bf}{bf_diff}% | Bel: {sign_w}{waist_diff}cm"

    await update.message.reply_text(msg, parse_mode="Markdown")

    # Send chart if enough data
    if len(measurements) >= 2:
        buf = generate_bodyfat_chart(measurements)
        if buf:
            await update.message.reply_photo(photo=buf, caption="📈 Yağ Oranı & Bel Çevresi Takibi")

    return ConversationHandler.END

def generate_bodyfat_chart(measurements):
    if len(measurements) < 2:
        return None

    dates = [datetime.strptime(m['date'], "%Y-%m-%d") for m in measurements]
    bfs = [m['body_fat'] for m in measurements]
    waists = [m['waist'] for m in measurements]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    fig.patch.set_facecolor('#1a1a2e')

    for ax, vals, color, title, ylabel in [
        (ax1, bfs, '#ff6b6b', '🔥 Yağ Oranı (%)', '%'),
        (ax2, waists, '#4ecdc4', '📏 Bel Çevresi (cm)', 'cm'),
    ]:
        ax.plot(dates, vals, 'o-', color=color, linewidth=2.5, markersize=8, markerfacecolor='white')
        ax.fill_between(dates, vals, alpha=0.15, color=color)
        ax.set_facecolor('#16213e')
        ax.set_title(title, color='white', fontsize=13, fontweight='bold')
        ax.set_ylabel(ylabel, color='white')
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

    fig.suptitle('Vücut Kompozisyonu Takibi', color='white', fontsize=14, fontweight='bold')
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close()
    return buf
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
    context.user_data['current_sets'] = []

    history = get_exercise_history(ex_name)
    prev_text = ""
    if history:
        last = history[-1]
        sets_str = " | ".join([f"{s['agirlik']}x{s['tekrar']}" for s in last['sets']])
        prev_text = f"\n📋 Son kayıt ({last['date'].strftime('%d/%m')}): {sets_str}"

    await query.edit_message_text(
        f"💪 *{ex_name}*{prev_text}\n\n"
        f"*1. Set* — Ağırlık ve tekrarı gir:\n"
        f"Örnek: `50x10`\n\n"
        f"Hareketi bitirmek için /bitti\\_hareket yaz.",
        parse_mode="Markdown"
    )
    return ENTER_SET

async def set_gir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    gun = context.user_data['gun']
    ex_name = context.user_data['exercise']
    current_sets = context.user_data.get('current_sets', [])

    # Parse single set: "50x10"
    try:
        if 'x' not in text.lower():
            raise ValueError()
        w, r = text.lower().split('x')
        new_set = {"agirlik": float(w.strip()), "tekrar": int(r.strip())}
    except:
        await update.message.reply_text("⚠️ Format: `50x10` (ağırlık x tekrar)", parse_mode="Markdown")
        return ENTER_SET

    current_sets.append(new_set)
    context.user_data['current_sets'] = current_sets
    set_no = len(current_sets)

    # Show sets so far
    sets_so_far = " | ".join([f"{s['agirlik']}x{s['tekrar']}" for s in current_sets])
    next_set_no = set_no + 1

    await update.message.reply_text(
        f"✅ *{set_no}. Set kaydedildi:* {new_set['agirlik']}kg x {new_set['tekrar']} tekrar\n"
        f"📊 Şu ana kadar: {sets_so_far}\n\n"
        f"*{next_set_no}. Set* — Ağırlık ve tekrarı gir:\n"
        f"Örnek: `60x8`\n\n"
        f"Hareketi bitirmek için /bitti\\_hareket yaz.",
        parse_mode="Markdown"
    )
    return ENTER_SET

async def bitti_hareket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gun = context.user_data.get('gun')
    ex_name = context.user_data.get('exercise')
    sets = context.user_data.get('current_sets', [])

    if not sets:
        await update.message.reply_text("⚠️ Hiç set girmedin, önce en az 1 set gir.")
        return ENTER_SET

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
            pr_text = f"\n🏆 *YENİ REKOR! {prev_max}kg → {max_w}kg* 🎉"

    sets_text = " | ".join([f"{s['agirlik']}kg x{s['tekrar']}" for s in sets])

    exercises = PROGRAM[gun]['exercises']
    keyboard = []
    for i, ex in enumerate(exercises):
        done = "✅ " if (today in data and gun in data[today] and ex in data[today][gun]) else ""
        keyboard.append([InlineKeyboardButton(f"{done}{i+1}. {ex}", callback_data=f"ex_{i}")])
    keyboard.append([InlineKeyboardButton("🏁 Bitti, grafik göster", callback_data="ex_done")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ *{ex_name}* tamamlandı! ({len(sets)} set)\n"
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
        "/antrenman — Antrenman verisi gir\n"
        "/grafik — Hareket güç grafikleri\n"
        "/ozet — Haftalık özet\n"
        "/kilo — Vücut ağırlığı gir\n"
        "/vucut — Yağ oranı & BMI hesabı\n"
        "/koc — AI koçunla konuş\n"
        "/program — Haftalık programı gör\n"
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
            ENTER_SET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_gir),
                CommandHandler("bitti_hareket", bitti_hareket),
            ],
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
    
    vucut_conv = ConversationHandler(
        entry_points=[CommandHandler("vucut", vucut_analiz_baslat)],
        states={
            ENTER_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, boy_gir),
                           CommandHandler("atla", boy_gir)],
            ENTER_NECK: [MessageHandler(filters.TEXT & ~filters.COMMAND, boyun_gir)],
            ENTER_WAIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bel_gir)],
        },
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
    app.add_handler(vucut_conv)
    
    logger.info("Bot başlatıldı!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
