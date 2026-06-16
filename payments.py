from __future__ import annotations
import hashlib, hmac, time, uuid, logging
from collections import defaultdict
import requests
from flask import request, jsonify
from config import UPIGATEWAY_API_KEY, UPIGATEWAY_SECRET, WEBHOOK_URL, MIN_RECHARGE_PAISA, MAX_SINGLE_RECHARGE_PAISA, RECHARGE_RATE_LIMIT_PER_HOUR, MAX_WALLET_BALANCE_PAISA
from db import get_user, log_order, confirm_order, credit_wallet
logger=logging.getLogger("GodModeV3")
_timestamps=defaultdict(list)

def verify_signature(payload: bytes, signature: str) -> bool:
    if not UPIGATEWAY_SECRET: return True
    expected=hmac.new(UPIGATEWAY_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def rate_limit(user_id:int) -> bool:
    now=time.time(); hour=now-3600
    _timestamps[user_id]=[x for x in _timestamps[user_id] if x>hour]
    if len(_timestamps[user_id])>=RECHARGE_RATE_LIMIT_PER_HOUR: return False
    _timestamps[user_id].append(now); return True

def create_order(user_id:int, amount_rs: float) -> dict:
    amount=int(round(amount_rs*100))
    if amount < MIN_RECHARGE_PAISA: return {"ok":False,"error":f"Minimum recharge is ₹{MIN_RECHARGE_PAISA/100:.0f}"}
    if amount > MAX_SINGLE_RECHARGE_PAISA: return {"ok":False,"error":"Amount too high"}
    if not UPIGATEWAY_API_KEY: return {"ok":False,"error":"Payment service unavailable"}
    if not rate_limit(user_id): return {"ok":False,"error":"Too many recharge attempts"}
    u=get_user(user_id)
    if u["balance_paisa"]+amount > MAX_WALLET_BALANCE_PAISA: return {"ok":False,"error":"Wallet limit exceeded"}
    txn=f"GMB-{user_id}-{uuid.uuid4().hex[:10].upper()}"
    log_order(txn,user_id,amount)
    payload={"key":UPIGATEWAY_API_KEY,"client_txn_id":txn,"amount":f"{amount_rs:.2f}","p_info":"GodMode Credits","customer_name":f"User{user_id}","customer_email":f"{user_id}@godmodebot.in","customer_mobile":"9999999999","redirect_url":f"{WEBHOOK_URL}/webhook/payment" if WEBHOOK_URL else "","udf1":str(user_id)}
    try:
        r=requests.post("https://api.upigateway.com/v1/create_order",json=payload,timeout=15)
        data=r.json()
        if data.get("status"):
            return {"ok":True,"url":data["data"]["payment_url"],"txn_id":txn}
        return {"ok":False,"error":data.get("msg","Payment gateway error")}
    except Exception as e:
        logger.exception("UPI create order failed")
        return {"ok":False,"error":"Payment service unavailable"}

def handle_payment_webhook() -> tuple:
    raw=request.get_data(); sig=request.headers.get("X-Signature","")
    if not verify_signature(raw,sig): return jsonify({"error":"invalid_signature"}),401
    data=request.get_json(silent=True) or request.form.to_dict()
    logger.info("payment webhook: %s", {k:v for k,v in data.items() if k.lower() not in ("key","signature")})
    status=str(data.get("status","")).upper(); txstatus=str(data.get("txStatus","")).upper()
    if status not in ("SUCCESS","TRUE") and txstatus != "SUCCESS": return jsonify({"result":"ignored"}),200
    txn=str(data.get("client_txn_id", data.get("clientTxnId", "")))
    ref=str(data.get("orderId", data.get("utr", data.get("gateway_ref", ""))))
    if not txn: return jsonify({"error":"missing_txn"}),400
    order=confirm_order(txn,ref)
    if not order: return jsonify({"result":"already_processed"}),200
    newbal=credit_wallet(order["user_id"], order["amount_paisa"], f"recharge:{txn}")
    return jsonify({"result":"credited","user_id":order["user_id"],"balance":newbal}),200
