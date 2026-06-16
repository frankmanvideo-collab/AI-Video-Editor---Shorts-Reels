from __future__ import annotations
import asyncio, logging, signal, threading
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from config import *
from db import init_db, get_user, save_session, load_session, clear_session, set_balance, stats
from keyboards import *
from jobs import enqueue, worker_loop, video_queue as _vq, service_price, service_max, SERVICE_PRICE
import jobs
from payments import create_order, handle_payment_webhook
from utils import rupees_str, escape_md, cleanup_old_files

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
logger=logging.getLogger("GodModeV3")
flask_app=Flask(__name__)

@flask_app.route("/health")
def health(): return jsonify({"status":"ok","version":BOT_VERSION}),200
@flask_app.route("/webhook/payment", methods=["POST"])
def payment_webhook(): return handle_payment_webhook()

def run_flask():
    try:
        from waitress import serve
        serve(flask_app, host="0.0.0.0", port=FLASK_PORT)
    except Exception:
        flask_app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)

async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; get_user(u.id, u.username or "")
    await update.message.reply_text(
        f"🎬 *AI Reel Growth Editor*\n\nSend raw video\. Get viral\-ready reel or audit report\.\n\n"
        "🎁 Free Sample: 15s once\n📊 Mini Audit: ₹19/reel\n🔥 Full Roast: ₹39/reel\n🎬 Edit 60s: ₹49\n🚀 Viral Pack 2min: ₹79\n\n"
        "Commands: /balance /recharge /help", parse_mode=ParseMode.MARKDOWN_V2)
async def help_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send a video up to 2 minutes and choose Audit or Edit\. Bot adds hooks, captions, BGM, CTA, hashtags and viral score\.", parse_mode=ParseMode.MARKDOWN_V2)
async def balance(update:Update, context:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; d=get_user(u.id)
    await update.message.reply_text(f"👛 Balance: *{escape_md(rupees_str(d['balance_paisa']))}*\n🎁 Free Sample: {'Used' if d['free_sample_used'] else 'Available'}", parse_mode=ParseMode.MARKDOWN_V2)
async def recharge(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💳 Choose recharge amount:", reply_markup=recharge_keyboard())
async def stats_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return
    s=stats(); q=jobs.video_queue.qsize() if jobs.video_queue else 0
    await update.message.reply_text(f"Users: {s['users']}\nRevenue: {rupees_str(s['revenue'])}\nWallets: {rupees_str(s['wallet'])}\nDB Jobs: {s['jobs']}\nQueue: {q}")
async def setbalance(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return
    if len(context.args)<2: await update.message.reply_text("Usage: /setbalance user_id amount_rs"); return
    uid=int(context.args[0]); amt=int(float(context.args[1])*100); set_balance(uid,amt,"admin")
    await update.message.reply_text(f"Set {uid} to {rupees_str(amt)}")

async def handle_video(update:Update, context:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; msg=update.message; vid=msg.video or msg.document
    if not vid: return
    size=(vid.file_size or 0)/(1024*1024)
    if size > MAX_FILE_SIZE_MB:
        await msg.reply_text(f"❌ Video too large\nMax allowed: {MAX_FILE_SIZE_MB}MB\nBest: MP4 under {MAX_FILE_SIZE_MB}MB, up to 2 minutes."); return
    mime=getattr(vid,"mime_type","") or ""
    if mime and mime not in ALLOWED_VIDEO_MIMES:
        await msg.reply_text("❌ Unsupported video format. Please send MP4/MOV/WebM."); return
    sess={"video_file_id":vid.file_id,"screenshots":[],"awaiting_custom_cta":False}
    save_session(u.id,sess)
    d=get_user(u.id)
    await msg.reply_text("🎬 Video received\!\n\nChoose what you want:", reply_markup=service_keyboard(not d["free_sample_used"]), parse_mode=ParseMode.MARKDOWN_V2)

async def handle_photo(update:Update, context:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; sess=load_session(u.id)
    if not sess: await update.message.reply_text("Send video first."); return
    shots=sess.get("screenshots",[])
    if len(shots)>=3: await update.message.reply_text("Max 3 screenshots."); return
    shots.append(update.message.photo[-1].file_id); sess["screenshots"]=shots; save_session(u.id,sess)
    await update.message.reply_text(f"Screenshot {len(shots)}/3 added.")

async def handle_text(update:Update, context:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; sess=load_session(u.id)
    if sess and sess.get("awaiting_custom_cta"):
        sess["cta"]=update.message.text.strip()[:120]; sess["awaiting_custom_cta"]=False; save_session(u.id,sess)
        await update.message.reply_text("✅ Custom CTA saved. Choose style:", reply_markup=style_keyboard())

async def callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); data=q.data or ""; uid=q.from_user.id
    if data.startswith("pay_"):
        amount=int(data.split("_")[1]); res=create_order(uid,amount)
        if res["ok"]: await q.edit_message_text(f"Pay ₹{amount}:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay Now", url=res["url"])]]) )
        else: await q.edit_message_text("❌ "+res["error"])
        return
    sess=load_session(uid) or {}
    if data.startswith("svc_"):
        kind=data.replace("svc_",""); sess["kind"]=kind; save_session(uid,sess)
        await q.edit_message_text("📱 Choose platform:", reply_markup=platform_keyboard()); return
    if data.startswith("platform_"):
        sess["platform"]=data.replace("platform_","").replace("_"," ").title(); save_session(uid,sess)
        await q.edit_message_text("🎯 Choose niche:", reply_markup=niche_keyboard()); return
    if data.startswith("niche_"):
        sess["niche"]=data.replace("niche_","").replace("_"," ").title(); save_session(uid,sess)
        await q.edit_message_text("🚀 Choose goal:", reply_markup=goal_keyboard()); return
    if data.startswith("goal_"):
        sess["goal"]=data.replace("goal_","").replace("_"," ").title(); save_session(uid,sess)
        from ai_director import generic_hooks
        hooks=generic_hooks(sess); sess["hook_options"]=hooks; save_session(uid,sess)
        if sess.get("kind") in ("mini_audit","full_roast"):
            await show_confirm(q, uid, sess); return
        await q.edit_message_text("🧲 Choose hook:", reply_markup=hook_keyboard(hooks)); return
    if data.startswith("hook_"):
        v=data.replace("hook_","")
        if v.isdigit(): sess["selected_hook"]=sess.get("hook_options",[])[int(v)]
        else: sess["selected_hook"]=v
        save_session(uid,sess); await q.edit_message_text("📩 Choose CTA:", reply_markup=cta_keyboard()); return
    if data.startswith("cta_"):
        v=data.replace("cta_","")
        if v=="custom": sess["awaiting_custom_cta"]=True; save_session(uid,sess); await q.edit_message_text('Type your custom CTA, e.g. DM "LINK" for details'); return
        mapping={"DM_START":'DM "START" for details',"DM_LINK":'DM "LINK" for details',"COMMENT_YES":'Comment "YES" for part 2',"SAVE":"Save this reel","skip":"skip"}
        sess["cta"]=mapping.get(v,v); save_session(uid,sess); await q.edit_message_text("🎨 Choose style:", reply_markup=style_keyboard()); return
    if data.startswith("style_"):
        sess["style"]=data.replace("style_","").replace("_"," ").title(); save_session(uid,sess); await q.edit_message_text("🌐 Choose language:", reply_markup=lang_keyboard()); return
    if data.startswith("lang_"):
        sess["lang"]=data.replace("lang_","").replace("_"," "); save_session(uid,sess); await q.edit_message_text("📍 Caption placement:", reply_markup=placement_keyboard()); return
    if data.startswith("place_"):
        sess["placement"]=data.replace("place_",""); save_session(uid,sess); await show_confirm(q, uid, sess); return
    if data=="cancel_job": clear_session(uid); await q.edit_message_text("Cancelled."); return
    if data=="confirm_job":
        kind=sess.get("kind","edit120"); price=service_price(kind); ok,jobid=await enqueue(context.bot,uid,kind,sess)
        if not ok: await q.edit_message_text("❌ "+jobid); return
        clear_session(uid); pos=jobs.video_queue.qsize() if jobs.video_queue else 1
        await q.edit_message_text(f"📋 Queue Position: #{pos}\nI’ll notify you when processing starts."); return

async def show_confirm(q, uid:int, sess:dict):
    kind=sess.get("kind","edit120"); price=service_price(kind); maxd=service_max(kind)
    u=get_user(uid)
    txt=(f"📋 Confirm\n\nPack: {kind}\nMax duration: {maxd:.0f}s\nPrice: {rupees_str(price) if price else 'FREE'}\nBalance: {rupees_str(u['balance_paisa'])}\n\nProceed?")
    await q.edit_message_text(txt, reply_markup=confirm_keyboard())

async def post_init(app:Application):
    cleanup_old_files(DOWNLOADS_DIR,3600)
    jobs.video_queue=asyncio.Queue()
    for _ in range(WORKER_COUNT): asyncio.create_task(worker_loop())
    logger.info("GodMode V3 started")

def main():
    init_db(); cleanup_old_files(DOWNLOADS_DIR,3600)
    threading.Thread(target=run_flask, daemon=True).start()
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("help",help_cmd)); app.add_handler(CommandHandler("balance",balance)); app.add_handler(CommandHandler("recharge",recharge)); app.add_handler(CommandHandler("stats",stats_cmd)); app.add_handler(CommandHandler("setbalance",setbalance))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
if __name__=="__main__": main()
