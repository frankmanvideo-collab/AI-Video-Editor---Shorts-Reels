
---

# 7. `SECURITY_NOTES.md`

```md
# Security Notes for GodMode Video Bot

## Current hardened points

- Wallet debit uses atomic SQL update: prevents negative balance race conditions.
- Payment webhook uses order table and `processed_at IS NULL`: prevents double credit from duplicate webhooks.
- Wallet credit amount is read from your own `order_payments` database row, not trusted from webhook payload.
- Queue limit prevents unlimited render jobs from crashing the server.
- One active job per user prevents one user spamming many renders.
- File size and duration limits reduce server abuse.
- Secrets are loaded from environment variables, not hard-coded.

## Important production warnings

1. Do not upload `.env` to GitHub.
2. Do not keep `UPIGATEWAY_SECRET` empty in final production if UPI Gateway supports webhook signing.
3. If UPI Gateway does not provide a webhook signing secret, use their transaction/status verification API before crediting wallet.
4. Always use HTTPS webhook URL for payments.
5. Keep `/data` as persistent storage because wallet database is stored there.
6. Keep backups of `/data/godmode_wallet.db`.
7. Start with 1 render worker. Multiple workers need bigger VPS.

## Main money-loss risks

- Fake webhook if webhook secret/status verification is not enabled.
- Lost database if hosting storage is not persistent.
- User pays but webhook URL is wrong/offline.
- Gateway sends different field names than code expects.

## Recommended demo setup

- Use Koyeb/Render free only for demo/small tests.
- Use small videos first.
- Check `/health` URL before testing payment webhook.
- Test payment with ₹49 recharge first.

## Payment webhook expected fields

The code accepts webhook success when:

- `status` is `SUCCESS` or `TRUE`, OR
- `txStatus` is `SUCCESS`

And it expects transaction id in:

- `client_txn_id` or `clientTxnId`

And gateway reference from:

- `orderId`, `utr`, or `gateway_ref`

If your gateway sends different fields, update `payment_webhook()` in `bot.py`.
